from __future__ import annotations

from datetime import UTC, datetime

from pymongo import DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.ids import new_id


class ActiveRunError(Exception):
    pass


class ThreadNotFoundError(Exception):
    pass


_RUN_FIELDS = (
    "id", "threadId", "status", "startedAt", "finishedAt",
    "assistantMessageId", "error",
)


def _now() -> datetime:
    return datetime.now(UTC)


def _without_id(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {key: value for key, value in row.items() if key != "_id"}


def _run_view(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {key: row[key] for key in _RUN_FIELDS if key in row}


class AgentRepository:
    def __init__(self, database) -> None:
        self.database = database

    def default_thread(self, case_id: str, owner_id: str) -> dict:
        row = self.database.agent_threads.find_one_and_update(
            {"caseId": case_id, "ownerId": owner_id, "isDefault": True},
            _default_thread_update(case_id, owner_id),
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return _without_id(row)

    def thread(self, thread_id: str, case_id: str, owner_id: str) -> dict:
        row = self.database.agent_threads.find_one(
            {"id": thread_id, "caseId": case_id, "ownerId": owner_id}
        )
        if not row:
            raise ThreadNotFoundError
        return _without_id(row)

    def messages(self, thread_id: str, session=None) -> list[dict]:
        rows = self.database.agent_messages.find(
            {"threadId": thread_id}, session=session
        ).sort([("createdAt", 1), ("id", 1)])
        return [_without_id(row) for row in rows]

    def active_run(self, thread_id: str, session=None) -> dict | None:
        row = self.database.agent_runs.find_one(
            {"threadId": thread_id, "status": "active"}, session=session
        )
        return _run_view(row)

    def latest_run(self, thread_id: str, session=None) -> dict | None:
        row = self.database.agent_runs.find_one(
            {"threadId": thread_id},
            sort=[("startedAt", DESCENDING), ("id", DESCENDING)],
            session=session,
        )
        return _run_view(row)

    def snapshot(self, thread: dict) -> dict:
        return _transaction(self.database, lambda session: self._snapshot(thread, session))

    def _snapshot(self, thread: dict, session) -> dict:
        current = self.database.agent_threads.find_one({"id": thread["id"]}, session=session)
        return {
            "id": current["id"],
            "caseId": current["caseId"],
            "messages": self.messages(current["id"], session),
            "activeRun": self.active_run(current["id"], session),
            "latestRun": self.latest_run(current["id"], session),
        }

    def start_run(self, thread, user_id, parts, metadata, assistant_id) -> dict:
        try:
            run = _transaction(
                self.database,
                lambda session: self._start_run(
                    thread, user_id, parts, metadata, assistant_id, session
                ),
            )
        except DuplicateKeyError as error:
            raise ActiveRunError from error
        return _without_id(run)

    def _start_run(self, thread, user_id, parts, metadata, assistant_id, session):
        message, run = _new_run_documents(
            thread, user_id, parts, metadata, assistant_id
        )
        self.database.agent_messages.insert_one(message, session=session)
        self.database.agent_runs.insert_one(run, session=session)
        self.database.agent_threads.update_one(
            {"id": thread["id"]},
            {"$set": {"activeRunId": run["id"], "updatedAt": _now()}},
            session=session,
        )
        return run

    def complete_run(self, run_id: str, assistant: dict) -> bool:
        return _transaction(
            self.database, lambda session: self._complete_run(run_id, assistant, session)
        )

    def _complete_run(self, run_id: str, assistant: dict, session) -> bool:
        run = self.database.agent_runs.find_one(
            {"id": run_id, "status": "active"}, session=session
        )
        if not run:
            return False
        assistant["createdAt"] = _now()
        self.database.agent_messages.insert_one(assistant, session=session)
        self._finish_record(run_id, "completed", {"assistantMessageId": assistant["id"]}, session)
        self._clear_active(run["threadId"], run_id, session)
        return True

    def fail_run(self, run_id: str) -> bool:
        return self._finish(run_id, "failed", {"error": "AI 服务暂不可用"})

    def cancel_run(self, run_id: str) -> bool:
        return self._finish(run_id, "cancelled", {"error": "运行已取消"})

    def _finish(self, run_id: str, status: str, fields: dict) -> bool:
        return _transaction(
            self.database,
            lambda session: self._finish_transaction(run_id, status, fields, session),
        )

    def _finish_transaction(self, run_id, status, fields, session) -> bool:
        run = self._finish_record(run_id, status, fields, session)
        if not run:
            return False
        self._clear_active(run["threadId"], run_id, session)
        return True

    def _finish_record(self, run_id, status, fields, session):
        return self.database.agent_runs.find_one_and_update(
            {"id": run_id, "status": "active"},
            {"$set": {"status": status, "finishedAt": _now(), **fields}},
            return_document=ReturnDocument.AFTER,
            session=session,
        )

    def _clear_active(self, thread_id: str, run_id: str, session) -> None:
        self.database.agent_threads.update_one(
            {"id": thread_id, "activeRunId": run_id},
            {"$set": {"activeRunId": None, "lastRunId": run_id, "updatedAt": _now()}},
            session=session,
        )


def _default_thread_update(case_id: str, owner_id: str) -> dict:
    now = _now()
    return {"$setOnInsert": _default_thread(case_id, owner_id, now), "$set": {"updatedAt": now}}


def _default_thread(case_id: str, owner_id: str, now: datetime) -> dict:
    return {
        "id": new_id("thread"), "caseId": case_id, "ownerId": owner_id,
        "isDefault": True, "activeRunId": None, "lastRunId": None, "createdAt": now,
    }


def _new_run_documents(thread, user_id, parts, metadata, assistant_id):
    now = _now()
    run_id, message_id = new_id("run"), new_id("message")
    message = {
        "id": message_id, "threadId": thread["id"], "runId": run_id,
        "role": "user", "metadata": metadata, "parts": parts, "createdAt": now,
    }
    run = {
        "id": run_id, "threadId": thread["id"], "userId": user_id,
        "userMessageId": message_id, "assistantMessageId": assistant_id,
        "status": "active", "startedAt": now,
    }
    return message, run


def _transaction(database, callback):
    with database.client.start_session() as session:
        return session.with_transaction(callback)
