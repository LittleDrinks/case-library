from __future__ import annotations

import atexit
import asyncio
import os
from threading import Event, Lock, Thread

from pymongo import MongoClient
from pymongo.monitoring import CommandListener
from pydantic_ai import Agent
from pydantic_ai.models.function import FunctionModel

from app.core import database as database_module


ANSWER = "隔离 FunctionModel 回答：已依据当前案例完成分析。"
AGENT_COLLECTIONS = {"agent_messages", "agent_runs", "agent_thread_events"}
TERMINAL_LABELS = ("assistant-message", "terminal-run", "terminal-event")


def _reservation_target(command):
    query = command.get("query", {})
    required = {"id", "activeRunId", "eventSeq", "nextMessageSeq"}
    if command.get("findAndModify") != "agent_threads" or not required <= query.keys():
        return None
    if query["activeRunId"] is not None or not command.get("lsid"):
        return None
    return query["id"], command["lsid"]["id"]


def _change_label(change, document):
    collection = change["ns"]["coll"]
    if collection == "agent_messages" and document.get("role") == "assistant":
        return "assistant-message", document["runId"]
    if collection == "agent_runs" and document.get("status") == "completed":
        return "terminal-run", document["id"]
    if collection == "agent_thread_events" and document.get("type") == "run.completed":
        return "terminal-event", document["runId"]
    return None


class _TerminalRetryGate(CommandListener):
    def __init__(self, uri: str, database_name: str) -> None:
        self._lock = Lock()
        self._attempts = {}
        self._states = {}
        self._stop = Event()
        self._observer = MongoClient(uri, appName="agent-e2e-gate-observer")
        self._database = self._observer[database_name]
        self._thread = Thread(target=self._observe, daemon=True)
        self._thread.start()

    def started(self, event) -> None:
        target = _reservation_target(event.command)
        if target is None:
            return
        thread_id, session_id = target
        with self._lock:
            key = (thread_id, session_id)
            self._attempts[key] = self._attempts.get(key, 0) + 1
            state = self._states.setdefault(thread_id, {"labels": [], "runId": None, "gate": Event()})
        if self._attempts[key] > 1 and not state["gate"].wait(15):
            raise RuntimeError("winner terminal Change Stream was not observed")

    def succeeded(self, _event) -> None:
        return None

    def failed(self, _event) -> None:
        return None

    def _observe(self) -> None:
        pipeline = [{"$match": {"ns.coll": {"$in": list(AGENT_COLLECTIONS)}}}]
        try:
            with self._database.watch(
                pipeline, full_document="updateLookup", max_await_time_ms=100
            ) as stream:
                while not self._stop.is_set():
                    change = stream.try_next()
                    if change:
                        self._record(change)
        except Exception:
            return None

    def _record(self, change) -> None:
        document = change.get("fullDocument") or {}
        thread_id = document.get("threadId")
        label = _change_label(change, document)
        if not thread_id or not label:
            return
        name, run_id = label
        with self._lock:
            state = self._states.get(thread_id)
            if not state or name != TERMINAL_LABELS[len(state["labels"])]:
                return
            if state["runId"] and state["runId"] != run_id:
                return
            state["runId"] = run_id
            state["labels"].append(name)
            if len(state["labels"]) == len(TERMINAL_LABELS):
                state["gate"].set()

    def close(self) -> None:
        self._stop.set()
        self._observer.close()
        self._thread.join(timeout=2)


_gate = None
_gate_client = None
if os.getenv("AGENT_E2E_TERMINAL_GATE") == "true":
    _gate = _TerminalRetryGate(os.environ["MONGODB_URI"], os.environ["MONGODB_DB_NAME"])
    _gate_client = MongoClient(os.environ["MONGODB_URI"], event_listeners=[_gate])
    database_module.connect = lambda settings: (_gate_client, _gate_client[settings.mongo_database])


def _close_gate() -> None:
    if _gate:
        _gate.close()
    if _gate_client:
        _gate_client.close()


atexit.register(_close_gate)


from app.main import create_app


async def _stream(_messages, _info):
    delay = 0.25 if "并发" in str(_messages) else 0
    if delay:
        await asyncio.sleep(delay)
    for character in ANSWER:
        yield character


def _application():
    application = create_app()
    model = FunctionModel(stream_function=_stream, model_name="function-e2e")
    application.state.agent = Agent(
        model=model, output_type=str, name="case-library-agent-e2e"
    )
    return application


app = _application()
