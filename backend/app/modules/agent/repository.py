from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TypeVar

from pydantic import BaseModel
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.ids import new_id
from app.modules.agent.models import (
    AgentMessage,
    AgentRun,
    AgentSnapshot,
    AgentThreadEvent,
    AgentThread,
    TerminalRunStatus,
    ThreadEventType,
)


ModelT = TypeVar("ModelT", bound=BaseModel)
RUN_OWNER_LEASE_SECONDS = 15


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

    def renew_run_owner(self, run_id: str, owner_id: str) -> bool:
        now = _now()
        row = self.database.agent_runs.find_one_and_update(
            _owned_query(run_id, owner_id, now),
            {"$set": {"ownerExpiresAt": now + _owner_delta()}},
            return_document=ReturnDocument.AFTER,
        )
        return row is not None

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
            event_seq=current.event_seq,
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
        client_request_id: str | None = None,
        owner_id: str | None = None,
    ) -> AgentRun:
        try:
            run = _transaction(self.database, lambda session: self._start_run(
                thread, user_id, parts, metadata, assistant_id, client_request_id,
                owner_id, session,
            ))
        except DuplicateKeyError as error:
            raise ActiveRunError from error
        return run

    def _start_run(
        self, thread, user_id, parts, metadata, assistant_id, client_request_id,
        owner_id, session
    ) -> AgentRun:
        run_id, message_id = new_id("run"), new_id("message")
        message_seq = self._reserve_start(thread, run_id, client_request_id, session)
        message, run = _new_run_documents(
            thread, user_id, parts, metadata, assistant_id, message_seq,
            client_request_id, run_id, message_id, owner_id,
        )
        self._insert_start_records(message, run, session)
        self._append_start_events(thread.id, run, message.id, session)
        return run

    def _insert_start_records(
        self, message: AgentMessage, run: AgentRun, session
    ) -> None:
        self.database.agent_runs.insert_one(
            _run_document(run), session=session
        )
        self.database.agent_messages.insert_one(
            message.model_dump(by_alias=True, mode="python", exclude_none=True),
            session=session,
        )

    def _reserve_start(
        self, thread: AgentThread, run_id: str, client_request_id: str | None, session
    ) -> int:
        if self._client_request_exists(thread.id, client_request_id, session):
            raise ActiveRunError
        current = self.database.agent_threads.find_one_and_update(
            {
                "id": thread.id,
                "activeRunId": None,
                "eventSeq": thread.event_seq,
                "nextMessageSeq": thread.next_message_seq,
            },
            {"$inc": {"nextMessageSeq": 1}, "$set": {"activeRunId": run_id, "updatedAt": _now()}},
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        if current is None:
            raise ActiveRunError
        return current["nextMessageSeq"]

    def _client_request_exists(self, thread_id: str, client_request_id: str | None, session) -> bool:
        return bool(client_request_id and self.database.agent_runs.find_one(
            {"threadId": thread_id, "clientRequestId": client_request_id}, session=session
        ))

    def _append_start_events(
        self, thread_id: str, run: AgentRun, message_id: str, session
    ) -> None:
        self._append_event(thread_id, "message.created", run.id, {"messageId": message_id}, session)
        self._append_event(
            thread_id,
            "run.started",
            run.id,
            {"userMessageId": message_id, "assistantMessageId": run.assistant_message_id},
            session,
        )

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

    def complete_run(self, run_id: str, assistant: AgentMessage, owner_id: str | None = None) -> bool:
        return _transaction(
            self.database, lambda session: self._complete_run(run_id, assistant, session, owner_id)
        )

    def _complete_run(self, run_id: str, assistant: AgentMessage, session, owner_id=None) -> bool:
        run = _model_view(
            self.database.agent_runs.find_one(
                _active_query(run_id, owner_id), session=session
            ),
            AgentRun,
        )
        if not run:
            return False
        assistant = self._completed_assistant(run, assistant, session)
        self._persist_assistant(run, assistant, session, owner_id)
        self._finish_completed(run, assistant, session, owner_id)
        return True

    def _persist_assistant(self, run: AgentRun, assistant: AgentMessage, session, owner_id=None) -> None:
        self.database.agent_messages.insert_one(
            assistant.model_dump(by_alias=True, mode="python", exclude_none=True),
            session=session,
        )
        if self._append_event(
            run.thread_id, "message.created", run.id, {"messageId": assistant.id},
            session, require_active=True, owner_id=owner_id
        ) is None:
            raise RuntimeError("AI 运行已结束")

    def _finish_completed(self, run: AgentRun, assistant: AgentMessage, session, owner_id=None) -> None:
        fields = {"assistantMessageId": assistant.id}
        if not self._finish_record(run.id, "completed", fields, session, owner_id):
            raise RuntimeError("AI 运行已结束")
        self._clear_active(run.thread_id, run.id, session)
        self._append_event(run.thread_id, "run.completed", run.id, fields, session)

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

    def fail_run(self, run_id: str, owner_id: str | None = None) -> bool:
        return self._finish(run_id, "failed", {"error": "AI 服务暂不可用"}, owner_id)

    def cancel_run(self, run_id: str, owner_id: str | None = None) -> bool:
        return self._finish(run_id, "cancelled", {"error": "运行已取消"}, owner_id)

    def _finish(
        self, run_id: str, status: TerminalRunStatus, fields: dict, owner_id=None,
    ) -> bool:
        return _transaction(
            self.database,
            lambda session: self._finish_transaction(
                run_id, status, fields, session, owner_id
            ),
        )

    def _finish_transaction(
        self, run_id: str, status: TerminalRunStatus, fields: dict, session,
        owner_id=None,
    ) -> bool:
        run = self._finish_record(
            run_id, status, fields, session, owner_id
        )
        if not run:
            return False
        self._clear_active(run.thread_id, run_id, session)
        self._append_event(run.thread_id, _terminal_event(status), run_id, fields, session)
        return True

    def _finish_record(
        self, run_id: str, status: TerminalRunStatus, fields: dict, session,
        owner_id=None,
    ) -> AgentRun | None:
        row = self.database.agent_runs.find_one_and_update(
            _active_query(run_id, owner_id),
            {
                "$set": {"status": status, "finishedAt": _now(), **fields},
                "$unset": _terminal_unset(),
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        return _model_view(row, AgentRun)

    def append_event(
        self, thread_id: str, event_type: ThreadEventType, run_id: str,
        payload: dict[str, object], owner_id: str | None = None,
    ) -> bool:
        return _transaction(
            self.database,
            lambda session: self._append_active_event(
                thread_id, event_type, run_id, payload, session, owner_id
            ),
        )

    def _append_active_event(
        self, thread_id: str, event_type: ThreadEventType, run_id: str, payload: dict,
        session, owner_id=None
    ) -> bool:
        if not self._run_active(thread_id, run_id, session, owner_id):
            return False
        return self._append_event(
            thread_id, event_type, run_id, payload, session, owner_id=owner_id
        ) is not None

    def _run_active(self, thread_id: str, run_id: str, session, owner_id=None) -> bool:
        return self.database.agent_runs.find_one(
            _active_query(run_id, owner_id, thread_id), session=session
        ) is not None

    def _append_event(
        self,
        thread_id: str,
        event_type: ThreadEventType,
        run_id: str,
        payload: dict[str, object],
        session,
        require_active: bool = False,
        owner_id: str | None = None,
    ) -> AgentThreadEvent | None:
        if require_active and not self._run_active(thread_id, run_id, session, owner_id):
            return None
        event = _thread_event(
            thread_id, self._next_event_seq(thread_id, session), event_type, run_id, payload
        )
        self.database.agent_thread_events.insert_one(
            event.model_dump(by_alias=True, mode="python"), session=session
        )
        return event

    def _next_event_seq(self, thread_id: str, session) -> int:
        thread = self.database.agent_threads.find_one_and_update(
            {"id": thread_id},
            {"$inc": {"eventSeq": 1}, "$set": {"updatedAt": _now()}},
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        if thread is None:
            raise ThreadNotFoundError
        return thread["eventSeq"]

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
        "isDefault": True, "nextMessageSeq": 0, "eventSeq": 0, "activeRunId": None,
        "lastRunId": None, "createdAt": now,
    }


def _new_run_documents(
    thread: AgentThread, user_id, parts, metadata, assistant_id, message_seq: int,
    client_request_id: str | None, run_id: str, message_id: str,
    owner_id: str | None,
) -> tuple[AgentMessage, AgentRun]:
    now = _now()
    return (
        _new_user_message(thread, run_id, message_id, parts, metadata, message_seq, now),
        _new_active_run(
            thread, user_id, message_id, assistant_id, run_id, now, client_request_id,
            owner_id,
        ),
    )


def _new_user_message(
    thread, run_id, message_id, parts, metadata, message_seq, now
) -> AgentMessage:
    return AgentMessage(
        id=message_id, thread_id=thread.id, run_id=run_id, message_seq=message_seq,
        role="user", metadata=metadata, parts=parts, created_at=now,
    )


def _new_active_run(
    thread, user_id, message_id, assistant_id, run_id, now, client_request_id,
    owner_id,
) -> AgentRun:
    return AgentRun(
        id=run_id, thread_id=thread.id, user_id=user_id, user_message_id=message_id,
        assistant_message_id=assistant_id, client_request_id=client_request_id,
        status="active", started_at=now,
        owner_id=owner_id,
        owner_expires_at=now + _owner_delta() if owner_id else None,
    )


def _run_document(run: AgentRun) -> dict:
    document = run.model_dump(by_alias=True, mode="python", exclude_none=True)
    for field, alias in _OWNER_FIELDS:
        value = getattr(run, field)
        if value is not None and value != []:
            document[alias] = value
    return document


def _active_query(
    run_id: str, owner_id: str | None = None, thread_id: str | None = None,
) -> dict:
    query = {"id": run_id, "status": "active"}
    if thread_id:
        query["threadId"] = thread_id
    if owner_id:
        now = _now()
        query.update({
            "ownerId": owner_id,
            "ownerExpiresAt": {"$gt": now},
        })
    return query


def _owned_query(run_id: str, owner_id: str, now: datetime) -> dict:
    return {
        "id": run_id, "status": "active", "ownerId": owner_id,
        "ownerExpiresAt": {"$gt": now},
    }


def _owner_delta():
    return timedelta(seconds=RUN_OWNER_LEASE_SECONDS)


_OWNER_FIELDS = (("owner_id", "ownerId"), ("owner_expires_at", "ownerExpiresAt"))


def _terminal_unset() -> dict[str, str]:
    return {alias: "" for _field, alias in _OWNER_FIELDS}


def _terminal_event(status: TerminalRunStatus) -> ThreadEventType:
    return {
        "completed": "run.completed",
        "failed": "run.failed",
        "cancelled": "run.cancelled",
    }[status]


def _thread_event(
    thread_id: str, event_seq: int, event_type: ThreadEventType, run_id: str,
    payload: dict[str, object]
) -> AgentThreadEvent:
    return AgentThreadEvent(
        id=new_id("event"), thread_id=thread_id, event_seq=event_seq,
        event_type=event_type, run_id=run_id, payload=payload, created_at=_now(),
    )


def _transaction(database, callback):
    with database.client.start_session() as session:
        return session.with_transaction(callback)
