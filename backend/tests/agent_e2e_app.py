from __future__ import annotations

import atexit
import os
from threading import Event, Lock, Thread

from pymongo import MongoClient
from pymongo.monitoring import CommandListener
from app.core import database as database_module


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


def _snapshot_target(command):
    query = command.get("filter", {})
    if command.get("find") != "agent_runs" or "threadId" not in query:
        return None
    return query["threadId"]


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
        self._snapshots = {}
        self._stop = Event()
        self._watch_ready = Event()
        self._observer = MongoClient(uri, appName="agent-e2e-gate-observer")
        self._database = self._observer[database_name]
        self._thread = Thread(target=self._observe, daemon=True)
        self._thread.start()
        if not self._watch_ready.wait(5):
            raise RuntimeError("terminal Change Stream did not open")

    def started(self, event) -> None:
        target = _reservation_target(event.command)
        snapshot = _snapshot_target(event.command)
        with self._lock:
            if target:
                thread_id, session_id = target
                key = (thread_id, session_id)
                self._attempts[key] = self._attempts.get(key, 0) + 1
                state = self._states.setdefault(thread_id, self._new_state())
                retry = self._attempts[key] > 1
            else:
                retry = False
            if snapshot and not self._states.get(snapshot, {}).get("snapshotReady"):
                self._snapshots[event.request_id] = snapshot
        if target and retry and not state["gate"].wait(15):
            raise RuntimeError("winner terminal Change Stream was not observed")

    def succeeded(self, _event) -> None:
        snapshot = self._pop_snapshot(_event.request_id)
        if snapshot and self._claim_snapshot(snapshot):
            self._await_terminal(snapshot)

    def failed(self, _event) -> None:
        return None

    def _pop_snapshot(self, request_id):
        with self._lock:
            return self._snapshots.pop(request_id, None)

    def _claim_snapshot(self, thread_id: str) -> bool:
        with self._lock:
            state = self._states.setdefault(thread_id, self._new_state())
            if state["snapshotReady"]:
                return False
            state["snapshotReady"] = True
            return True

    def _await_terminal(self, thread_id: str) -> None:
        with self._lock:
            gate = self._states[thread_id]["gate"]
        if not gate.wait(15):
            raise RuntimeError("winner terminal Change Stream was not observed")

    def _observe(self) -> None:
        pipeline = [{"$match": {"ns.coll": {"$in": list(AGENT_COLLECTIONS)}}}]
        try:
            with self._database.watch(
                pipeline, full_document="updateLookup", max_await_time_ms=100
            ) as stream:
                self._watch_ready.set()
                while not self._stop.is_set():
                    change = stream.try_next()
                    if change:
                        self._record(change)
        except Exception:
            self._watch_ready.set()

    def _record(self, change) -> None:
        document = change.get("fullDocument") or {}
        thread_id = document.get("threadId")
        label = _change_label(change, document)
        if not thread_id or not label:
            return
        name, run_id = label
        with self._lock:
            state = self._states.get(thread_id)
            if not state or len(state["labels"]) >= len(TERMINAL_LABELS):
                return
            if name != TERMINAL_LABELS[len(state["labels"])]:
                return
            if state["runId"] and state["runId"] != run_id:
                return
            state["runId"] = run_id
            state["labels"].append(name)
            if len(state["labels"]) == len(TERMINAL_LABELS):
                state["gate"].set()

    def _new_state(self):
        return {"labels": [], "runId": None, "gate": Event(), "snapshotReady": False}

    def close(self) -> None:
        self._stop.set()
        self._observer.close()
        self._thread.join(timeout=2)


_gate = None
_gate_client = None
if os.getenv("AGENT_E2E_TERMINAL_GATE") == "true":
    _gate = _TerminalRetryGate(os.environ["MONGODB_URI"], os.environ["MONGODB_DB_NAME"])
    _gate_client = MongoClient(os.environ["MONGODB_URI"], event_listeners=[_gate])


def _connect_with_gate(settings):
    return _gate_client, _gate_client[settings.mongo_database]


if _gate_client:
    database_module.connect = _connect_with_gate


def _close_gate() -> None:
    if _gate:
        _gate.close()
    if _gate_client:
        _gate_client.close()


atexit.register(_close_gate)


def _application():
    from app.main import create_app

    return create_app()


app = _application()
