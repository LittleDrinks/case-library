from __future__ import annotations

from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.ids import new_id
from app.modules.agent.models import (
    AgentMessage,
    AgentRun,
    AgentSnapshot,
    AgentThread,
    TerminalRunStatus,
)


ModelT = TypeVar("ModelT", bound=BaseModel)


class ActiveRunError(Exception):
    pass


class ThreadNotFoundError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _without_id(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {key: value for key, value in row.items() if key != "_id"}


def _model_view(row: dict | None, model_type: type[ModelT]) -> ModelT | None:
    if row is None:
        return None
    return model_type.model_validate(_without_id(row))


class AgentRepository:
    def __init__(self, database) -> None:
        self.database = database

    def default_thread(self, case_id: str, owner_id: str) -> AgentThread:
        row = self.database.agent_threads.find_one_and_update(
            {"caseId": case_id, "ownerId": owner_id, "isDefault": True},
            _default_thread_update(case_id, owner_id),
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return _model_view(row, AgentThread)

    def thread(self, thread_id: str, case_id: str, owner_id: str) -> AgentThread:
        row = self.database.agent_threads.find_one(
            {"id": thread_id, "caseId": case_id, "ownerId": owner_id}
        )
        if not row:
            raise ThreadNotFoundError
        return _model_view(row, AgentThread)

    def messages(self, thread_id: str, session=None) -> list[AgentMessage]:
        rows = self.database.agent_messages.find(
            {"threadId": thread_id}, session=session
        ).sort([("messageSeq", ASCENDING)])
        return [_model_view(row, AgentMessage) for row in rows]

    def active_run(self, thread_id: str, session=None) -> AgentRun | None:
        row = self.database.agent_runs.find_one(
            {"threadId": thread_id, "status": "active"}, session=session
        )
        return _model_view(row, AgentRun)

    def latest_run(self, thread_id: str, session=None) -> AgentRun | None:
        row = self.database.agent_runs.find_one(
            {"threadId": thread_id},
            sort=[("startedAt", DESCENDING), ("id", DESCENDING)],
            session=session,
        )
        return _model_view(row, AgentRun)

    def snapshot(self, thread: AgentThread) -> AgentSnapshot:
        return _transaction(self.database, lambda session: self._snapshot(thread, session))

    def _snapshot(self, thread: AgentThread, session) -> AgentSnapshot:
        current = _model_view(
            self.database.agent_threads.find_one({"id": thread.id}, session=session),
            AgentThread,
        )
        if current is None:
            raise ThreadNotFoundError
        return AgentSnapshot(
            id=current.id,
            case_id=current.case_id,
            messages=self.messages(current.id, session),
            active_run=self.active_run(current.id, session),
            latest_run=self.latest_run(current.id, session),
        )

    def start_run(
        self,
        thread: AgentThread,
        user_id: str,
        parts: list[dict[str, object]],
        metadata: dict[str, object],
        assistant_id: str,
    ) -> AgentRun:
        try:
            run = _transaction(
                self.database,
                lambda session: self._start_run(
                    thread, user_id, parts, metadata, assistant_id, session
                ),
            )
        except DuplicateKeyError as error:
            raise ActiveRunError from error
        return run

    def _start_run(
        self, thread: AgentThread, user_id, parts, metadata, assistant_id, session
    ) -> AgentRun:
        message_seq = self._next_message_seq(thread.id, session)
        message, run = _new_run_documents(
            thread, user_id, parts, metadata, assistant_id, message_seq
        )
        self.database.agent_messages.insert_one(
            message.model_dump(by_alias=True, mode="python"), session=session
        )
        self.database.agent_runs.insert_one(
            run.model_dump(by_alias=True, mode="python"), session=session
        )
        self.database.agent_threads.update_one(
            {"id": thread.id},
            {"$set": {"activeRunId": run.id, "updatedAt": _now()}},
            session=session,
        )
        return run

    def _next_message_seq(self, thread_id: str, session) -> int:
        thread = self.database.agent_threads.find_one_and_update(
            {"id": thread_id},
            {"$inc": {"nextMessageSeq": 1}},
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        if thread is None:
            raise ThreadNotFoundError
        return thread["nextMessageSeq"]

    def complete_run(self, run_id: str, assistant: AgentMessage) -> bool:
        return _transaction(
            self.database, lambda session: self._complete_run(run_id, assistant, session)
        )

    def _complete_run(self, run_id: str, assistant: AgentMessage, session) -> bool:
        run = _model_view(
            self.database.agent_runs.find_one(
                {"id": run_id, "status": "active"}, session=session
            ),
            AgentRun,
        )
        if not run:
            return False
        assistant = self._completed_assistant(run, assistant, session)
        self.database.agent_messages.insert_one(
            assistant.model_dump(by_alias=True, mode="python"), session=session
        )
        self._finish_record(
            run_id, "completed", {"assistantMessageId": assistant.id}, session
        )
        self._clear_active(run.thread_id, run_id, session)
        return True

    def _completed_assistant(
        self, run: AgentRun, assistant: AgentMessage, session
    ) -> AgentMessage:
        if assistant.thread_id != run.thread_id or assistant.run_id != run.id:
            raise ValueError("assistant message does not belong to run")
        return assistant.model_copy(
            update={
                "message_seq": self._next_message_seq(run.thread_id, session),
                "created_at": _now(),
            }
        )

    def fail_run(self, run_id: str) -> bool:
        return self._finish(run_id, "failed", {"error": "AI 服务暂不可用"})

    def cancel_run(self, run_id: str) -> bool:
        return self._finish(run_id, "cancelled", {"error": "运行已取消"})

    def _finish(self, run_id: str, status: TerminalRunStatus, fields: dict) -> bool:
        return _transaction(
            self.database,
            lambda session: self._finish_transaction(run_id, status, fields, session),
        )

    def _finish_transaction(
        self, run_id: str, status: TerminalRunStatus, fields: dict, session
    ) -> bool:
        run = self._finish_record(run_id, status, fields, session)
        if not run:
            return False
        self._clear_active(run.thread_id, run_id, session)
        return True

    def _finish_record(
        self, run_id: str, status: TerminalRunStatus, fields: dict, session
    ) -> AgentRun | None:
        row = self.database.agent_runs.find_one_and_update(
            {"id": run_id, "status": "active"},
            {"$set": {"status": status, "finishedAt": _now(), **fields}},
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        return _model_view(row, AgentRun)

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
        "isDefault": True, "nextMessageSeq": 0, "activeRunId": None,
        "lastRunId": None, "createdAt": now,
    }


def _new_run_documents(
    thread: AgentThread, user_id, parts, metadata, assistant_id, message_seq: int
) -> tuple[AgentMessage, AgentRun]:
    now = _now()
    run_id, message_id = new_id("run"), new_id("message")
    return (
        _new_user_message(thread, run_id, message_id, parts, metadata, message_seq, now),
        _new_active_run(thread, user_id, message_id, assistant_id, run_id, now),
    )


def _new_user_message(
    thread, run_id, message_id, parts, metadata, message_seq, now
) -> AgentMessage:
    return AgentMessage(
        id=message_id, thread_id=thread.id, run_id=run_id, message_seq=message_seq,
        role="user", metadata=metadata, parts=parts, created_at=now,
    )


def _new_active_run(thread, user_id, message_id, assistant_id, run_id, now) -> AgentRun:
    return AgentRun(
        id=run_id, thread_id=thread.id, user_id=user_id, user_message_id=message_id,
        assistant_message_id=assistant_id, status="active", started_at=now,
    )


def _transaction(database, callback):
    with database.client.start_session() as session:
        return session.with_transaction(callback)
