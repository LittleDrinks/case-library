from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TypeVar

from pydantic import BaseModel
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.ids import new_id
from app.modules.agent import blocks
from app.modules.agent.models import (
    REVIEW_MODE,
    AgentArtifact,
    AgentMessage,
    AgentRun,
    AgentSnapshot,
    AgentThreadEvent,
    AgentThread,
    ArtifactTarget,
    TerminalRunStatus,
    ThreadEventType,
    write_view,
)
from app.modules.cases.published import version_readable
from app.modules.cases.versions import create_ai_version, create_ai_version_from_write


ModelT = TypeVar("ModelT", bound=BaseModel)
RUN_OWNER_LEASE_SECONDS = 15


class ActiveRunError(Exception):
    pass


class MessageNotFoundError(Exception):
    def __init__(self, message_id: str) -> None:
        super().__init__(message_id)
        self.message_id = message_id


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

    def default_thread(self, case_id: str, owner_id: str, version_id: str | None = None,
                       mode: str | None = None) -> AgentThread:
        try:
            row = self.database.agent_threads.find_one_and_update(
                {"caseId": case_id, "ownerId": owner_id, "isDefault": True,
                 "versionId": version_id, "mode": mode},
                _default_thread_update(case_id, owner_id, version_id, mode),
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            # 并发首建竞争：部分唯一索引拒绝败者插入，回读胜者文档。
            row = self.database.agent_threads.find_one(
                {"caseId": case_id, "ownerId": owner_id, "isDefault": True,
                 "versionId": version_id, "mode": mode}
            )
        return _model_view(row, AgentThread)

    def thread(self, thread_id: str, case_id: str, owner_id: str) -> AgentThread:
        row = self.database.agent_threads.find_one(
            {"id": thread_id, "caseId": case_id, "ownerId": owner_id}
        )
        if not row:
            raise ThreadNotFoundError
        return _model_view(row, AgentThread)

    def list_threads(self, case_id: str, owner_id: str, version_id: str | None = None,
                     mode: str | None = None) -> list[AgentThread]:
        rows = self.database.agent_threads.find(
            {"caseId": case_id, "ownerId": owner_id, "versionId": version_id,
             "mode": mode}
        ).sort([("updatedAt", DESCENDING), ("id", DESCENDING)])
        return [_model_view(row, AgentThread) for row in rows]

    def create_thread(
        self, case_id: str, owner_id: str, title: str | None = None,
        version_id: str | None = None, mode: str | None = None,
    ) -> AgentThread:
        now = _now()
        thread = AgentThread(
            id=new_id("thread"), case_id=case_id, owner_id=owner_id,
            version_id=version_id, mode=mode, title=title, is_default=False,
            created_at=now, updated_at=now,
        )
        self.database.agent_threads.insert_one(
            thread.model_dump(by_alias=True, mode="python", exclude_none=True)
        )
        return thread

    def rename_thread(
        self, thread_id: str, case_id: str, owner_id: str, title: str
    ) -> AgentThread:
        row = self.database.agent_threads.find_one_and_update(
            {"id": thread_id, "caseId": case_id, "ownerId": owner_id},
            {"$set": {"title": title}},
            return_document=ReturnDocument.AFTER,
        )
        if not row:
            raise ThreadNotFoundError
        return _model_view(row, AgentThread)

    def thread_by_id(self, thread_id: str, session=None) -> AgentThread | None:
        row = self.database.agent_threads.find_one(
            {"id": thread_id}, session=session
        )
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

    def runs(self, thread_id: str, session=None) -> list[AgentRun]:
        rows = self.database.agent_runs.find(
            {"threadId": thread_id}, session=session
        ).sort([("startedAt", ASCENDING), ("id", ASCENDING)])
        return [_model_view(row, AgentRun) for row in rows]

    def message(self, thread_id: str, message_id: str) -> AgentMessage | None:
        row = self.database.agent_messages.find_one(
            {"threadId": thread_id, "id": message_id}
        )
        return _model_view(row, AgentMessage)

    def latest_run(self, thread_id: str, session=None) -> AgentRun | None:
        row = self.database.agent_runs.find_one(
            {"threadId": thread_id},
            sort=[("startedAt", DESCENDING), ("id", DESCENDING)],
            session=session,
        )
        return _model_view(row, AgentRun)

    def renew_run_owner(self, run_id: str, owner_id: str) -> dict | None:
        now = _now()
        row = self.database.agent_runs.find_one_and_update(
            _owned_query(run_id, owner_id, now),
            {"$set": {"ownerExpiresAt": now + _owner_delta()}},
            return_document=ReturnDocument.AFTER,
        )
        return _without_id(row)

    def record_tool_timing(
        self, run_id: str, timing: dict[str, str], owner_id: str | None = None
    ) -> bool:
        row = self.database.agent_runs.find_one(_active_query(run_id, owner_id))
        if row is None:
            return False
        timings = {**(row.get("toolTimings") or {}), timing["toolCallId"]: timing}
        result = self.database.agent_runs.update_one(
            _active_query(run_id, owner_id), {"$set": {"toolTimings": timings}}
        )
        return result.matched_count == 1

    def snapshot(self, thread: AgentThread) -> AgentSnapshot:
        return _transaction(self.database, lambda session: self._snapshot(thread, session))

    def _snapshot(self, thread: AgentThread, session) -> AgentSnapshot:
        current = self._snapshot_thread(thread.id, session)
        return AgentSnapshot(
            id=current.id,
            case_id=current.case_id,
            version_id=current.version_id,
            title=current.title,
            event_seq=current.event_seq,
            messages=self.messages(current.id, session),
            artifacts=self._snapshot_artifacts(current, session),
            writes=self.write_views(current.id, session),
            runs=self.runs(current.id, session),
            active_run=self.active_run(current.id, session),
            latest_run=self.latest_run(current.id, session),
        )

    def _snapshot_thread(self, thread_id: str, session) -> AgentThread:
        current = _model_view(
            self.database.agent_threads.find_one({"id": thread_id}, session=session),
            AgentThread,
        )
        if current is None:
            raise ThreadNotFoundError
        return current

    def write_views(self, thread_id: str, session=None) -> list:
        """线程写入记录视图：撤销状态回显的服务端真源。"""
        rows = self.database.agent_writes.find(
            {"threadId": thread_id}, session=session
        ).sort([("createdAt", ASCENDING), ("id", ASCENDING)])
        return [write_view(row) for row in rows]

    def _snapshot_artifacts(self, thread: AgentThread, session) -> list[AgentArtifact]:
        revision = _case_revision(self.database, thread.case_id, session)
        return [
            expired_artifact_view(artifact, revision)
            for artifact in self.artifacts(thread.id, session)
        ]

    def events_after(
        self, thread_id: str, after_seq: int, limit: int = 200
    ) -> list[AgentThreadEvent]:
        rows = self.database.agent_thread_events.find(
            {"threadId": thread_id, "eventSeq": {"$gt": after_seq}}
        ).sort([("eventSeq", ASCENDING)]).limit(limit)
        return [_model_view(row, AgentThreadEvent) for row in rows]

    def artifacts(self, thread_id: str, session=None) -> list[AgentArtifact]:
        rows = self.database.agent_artifacts.find(
            {"threadId": thread_id}, session=session
        ).sort([("createdAt", ASCENDING), ("id", ASCENDING)])
        return [_model_view(row, AgentArtifact) for row in rows]

    def start_run(
        self, thread: AgentThread, user_id: str, parts: list[dict[str, object]],
        metadata: dict[str, object], assistant_id: str,
        client_request_id: str | None = None, owner_id: str | None = None,
        quota_ids: tuple[str, ...] = (), default_title: str | None = None,
        skill_bindings: list[dict[str, str]] | None = None,
        base_revision: int | None = None, target: ArtifactTarget | None = None,
        write_authorized: bool = False,
    ) -> AgentRun:
        try:
            run = _transaction(self.database, lambda session: self._start_run(
                thread, user_id, parts, metadata, assistant_id, client_request_id,
                owner_id, quota_ids, skill_bindings, session, default_title,
                base_revision, target, write_authorized,
            ))
        except DuplicateKeyError as error:
            raise ActiveRunError from error
        return run

    def _start_run(
        self, thread, user_id, parts, metadata, assistant_id, client_request_id,
        owner_id, quota_ids, skill_bindings, session, default_title=None,
        base_revision=None, target=None, write_authorized: bool = False,
    ) -> AgentRun:
        run_id, message_id = new_id("run"), new_id("message")
        message_seq = self._reserve_start(thread, run_id, client_request_id, session, default_title)
        message, run = _new_run_documents(
            thread, user_id, parts, metadata, assistant_id, message_seq,
            client_request_id, run_id, message_id, owner_id, quota_ids,
            skill_bindings, base_revision, target, write_authorized,
        )
        self._insert_start_records(message, run, session)
        self._append_start_events(thread.id, run, message.id, session)
        return run

    def retry_run(
        self,
        thread: AgentThread,
        user_message_id: str,
        assistant_id: str,
        owner_id: str | None = None,
        quota_ids: tuple[str, ...] = (),
        skill_bindings: list[dict[str, str]] | None = None,
        base_revision: int | None = None, target: ArtifactTarget | None = None,
        write_authorized: bool = False,
    ) -> AgentRun:
        """重试失败消息：新 Run 引用原用户消息，不插入新消息。"""
        try:
            return _transaction(self.database, lambda session: self._retry_run(
                thread, user_message_id, assistant_id, owner_id, quota_ids,
                skill_bindings, base_revision, target, write_authorized, session,
            ))
        except DuplicateKeyError as error:
            raise ActiveRunError from error

    def _retry_run(
        self, thread, user_message_id, assistant_id, owner_id, quota_ids,
        skill_bindings, base_revision, target, write_authorized, session,
    ) -> AgentRun:
        message = self.database.agent_messages.find_one(
            {"threadId": thread.id, "id": user_message_id, "role": "user"},
            session=session,
        )
        if message is None:
            raise MessageNotFoundError(user_message_id)
        run_id = new_id("run")
        if self._reserve_active(thread, run_id, session, bump=False) is None:
            raise ActiveRunError
        return self._insert_retry_run(
            thread, message, assistant_id, run_id, owner_id, quota_ids,
            skill_bindings,
            base_revision, target, write_authorized, session,
        )

    def _insert_retry_run(
        self, thread, message, assistant_id, run_id, owner_id, quota_ids,
        skill_bindings, base_revision, target, write_authorized, session,
    ) -> AgentRun:
        run = _new_retry_run(
            thread, message, assistant_id, run_id, owner_id, quota_ids,
            skill_bindings, base_revision, target, write_authorized,
        )
        self.database.agent_runs.insert_one(_run_document(run), session=session)
        self._append_event(
            thread.id, "run.started", run.id,
            {"userMessageId": message["id"], "assistantMessageId": assistant_id},
            session,
        )
        return run

    def request_cancel(self, run_id: str) -> AgentRun | None:
        """幂等标记活动 Run 为取消请求；由持有者通过 cancellation token 执行。"""
        row = self.database.agent_runs.find_one_and_update(
            {"id": run_id, "status": "active"},
            {"$set": {"cancelRequestedAt": _now()}},
            return_document=ReturnDocument.AFTER,
        )
        return _model_view(row, AgentRun)

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
        self, thread: AgentThread, run_id: str, client_request_id: str | None, session,
        default_title: str | None = None,
    ) -> int:
        if self._client_request_exists(thread.id, client_request_id, session):
            raise ActiveRunError
        current = self.database.agent_threads.find_one_and_update(
            _reservation_query(thread),
            {"$inc": {"nextMessageSeq": 1}, "$set": _start_fields(run_id, thread, default_title)},
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        if current is None:
            raise ActiveRunError
        return current["nextMessageSeq"]

    def _reserve_active(
        self, thread: AgentThread, run_id: str, session, bump: bool = True
    ) -> dict | None:
        update: dict = {"$set": {"activeRunId": run_id, "updatedAt": _now()}}
        if bump:
            update["$inc"] = {"nextMessageSeq": 1}
        return self.database.agent_threads.find_one_and_update(
            _reservation_query(thread),
            update,
            return_document=ReturnDocument.AFTER,
            session=session,
        )

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

    def complete_run(
        self, run_id: str, assistant: AgentMessage, owner_id: str | None = None,
        resources: list[dict[str, str]] | None = None,
        reader_case_id: str | None = None, reader_version_id: str | None = None,
        artifact: AgentArtifact | None = None,
        write_record: dict | None = None,
    ) -> bool:
        return _transaction(
            self.database,
            lambda session: self._complete_run(
                run_id, assistant, session, owner_id, resources,
                reader_case_id, reader_version_id,
                artifact,
                write_record,
            ),
        )

    def _complete_run(self, run_id: str, assistant: AgentMessage, session, owner_id=None,
                      resources=None, reader_case_id=None, reader_version_id=None,
                      artifact: AgentArtifact | None = None, write_record=None) -> bool:
        run = _model_view(
            self.database.agent_runs.find_one(_active_query(run_id, owner_id), session=session),
            AgentRun,
        )
        if not run:
            return False
        if reader_case_id and not self._reader_completion_allowed(
            reader_case_id, reader_version_id, run_id, session
        ):
            return self._finish_transaction(
                run_id, "cancelled", {"error": "运行已取消"}, session, owner_id
            )
        return self._complete_records(
            run, assistant, session, owner_id, resources, artifact, write_record
        )

    def _complete_records(
        self, run, assistant, session, owner_id, resources, artifact=None, write_record=None
    ) -> bool:
        version = self._persist_version(run, artifact, write_record, session)
        if artifact and artifact.kind == "document":
            assistant = _link_version(assistant, artifact.id, version, self._version_detail(run))
        if write_record and write_record.get("scope") == "document":
            assistant = _link_write_version(
                assistant, write_record["id"], version, self._version_detail(run)
            )
        assistant = self._completed_assistant(run, assistant, session)
        self._persist_assistant(run, assistant, session, owner_id)
        if artifact is not None and artifact.kind != "document":
            self._persist_artifact(run, artifact, session)
        self._finish_completed(run, assistant, session, owner_id, resources)
        return True

    def _persist_version(self, run, artifact, write_record, session):
        if artifact and artifact.kind == "document":
            document = blocks.structured_document(artifact.blocks)
            version = create_ai_version(self.database, artifact, run, document, session)
        elif write_record:
            version = create_ai_version_from_write(self.database, write_record, run, session)
        else:
            return None
        if version and self._append_event(
            run.thread_id, "version.created", run.id,
            {"versionId": version["id"]}, session,
        ) is None:
            raise RuntimeError("Thread 事件写入失败")
        return version

    def _version_detail(self, run) -> str:
        thread = self.database.agent_threads.find_one({"id": run.thread_id}, {"caseId": 1})
        case = self.database.cases.find_one({"id": thread["caseId"]}) if thread else None
        if case and case.get("revision") != run.base_revision:
            return "AI版本未保存：正文基线已变化，未创建独立版本"
        return "AI版本未保存：未满足独立版本保存条件"

    def _reader_completion_allowed(self, case_id, version_id, run_id, session) -> bool:
        case = self.database.cases.find_one_and_update(
            {"id": case_id}, {"$set": {"_readerCompletionFence": run_id}},
            return_document=ReturnDocument.AFTER, session=session,
        )
        version = self.database.case_versions.find_one(
            {"id": version_id, "caseId": case_id}, session=session
        ) if case and version_id else None
        return bool(
            case and version and version_readable(
                self.database, case, version_id, version, False, session=session
            )
        )

    def _persist_artifact(self, run: AgentRun, artifact: AgentArtifact, session) -> None:
        """修订候选与 tool.result、助手消息、事件尾部同事务对外可见。"""
        self.database.agent_artifacts.insert_one(
            artifact.model_dump(by_alias=True, mode="python"), session=session
        )
        if self._append_event(
            run.thread_id, "artifact.created", run.id,
            {"artifactId": artifact.id}, session,
        ) is None:
            raise RuntimeError("Thread 事件写入失败")

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

    def _finish_completed(self, run: AgentRun, assistant: AgentMessage, session, owner_id=None,
                          resources=None) -> None:
        fields: dict = {"assistantMessageId": assistant.id}
        if resources is not None:
            fields["resources"] = resources
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


def _link_version(
    assistant: AgentMessage, artifact_id: str, version: dict | None, detail: str
) -> AgentMessage:
    return assistant.model_copy(update={
        "parts": [_version_part(part, artifact_id, version, detail) for part in assistant.parts],
    })


def _version_part(part: dict, artifact_id: str, version: dict | None, detail: str) -> dict:
    output = part.get("output")
    if part.get("type") != "tool-propose_document" or not isinstance(output, dict):
        return part
    if output.get("artifactId") not in (artifact_id, None):
        return part
    if version:
        return {**part, "output": {"status": "created", "kind": "ai",
                                    "versionId": version["id"]}}
    return {**part, "output": {"status": "not_saved", "detail": detail}}


def _link_write_version(
    assistant: AgentMessage, write_id: str, version: dict | None, detail: str
) -> AgentMessage:
    return assistant.model_copy(update={
        "parts": [_write_version_part(part, write_id, version, detail) for part in assistant.parts],
    })


def _write_version_part(part: dict, write_id: str, version: dict | None, detail: str) -> dict:
    output = part.get("output")
    if part.get("type") != "tool-write_document" or not isinstance(output, dict):
        return part
    if output.get("id") not in (write_id, None):
        return part
    if version:
        return {**part, "output": {**output, "versionId": version["id"],
                                    "versionStatus": "created", "versionKind": "ai"}}
    return {**part, "output": {**output, "versionStatus": "not_saved",
                                "versionDetail": detail}}


def _default_thread_update(
    case_id: str, owner_id: str, version_id: str | None, mode: str | None = None,
) -> dict:
    now = _now()
    return {
        "$setOnInsert": _default_thread(case_id, owner_id, now, version_id, mode),
        "$set": {"updatedAt": now},
    }


def _start_fields(run_id: str, thread: AgentThread, default_title: str | None) -> dict:
    fields: dict = {"activeRunId": run_id, "updatedAt": _now()}
    if default_title is not None and thread.title is None:
        fields["title"] = default_title
    return fields


def _reservation_query(thread: AgentThread) -> dict:
    return {
        "id": thread.id, "activeRunId": None,
        "eventSeq": thread.event_seq, "nextMessageSeq": thread.next_message_seq,
    }


def _default_thread(
    case_id: str, owner_id: str, now: datetime, version_id: str | None,
    mode: str | None = None,
) -> dict:
    document = {
        "id": new_id("thread"), "caseId": case_id, "ownerId": owner_id,
        "isDefault": True, "nextMessageSeq": 0, "eventSeq": 0, "activeRunId": None,
        "lastRunId": None, "createdAt": now,
    }
    if version_id is not None:
        document["versionId"] = version_id
    if mode is not None:
        document["mode"] = mode
    return document


def _new_run_documents(
    thread: AgentThread, user_id, parts, metadata, assistant_id, message_seq: int,
    client_request_id: str | None, run_id: str, message_id: str,
    owner_id: str | None, quota_ids: tuple[str, ...],
    skill_bindings: list[dict[str, str]] | None = None,
    base_revision: int | None = None, target: ArtifactTarget | None = None,
    write_authorized: bool = False,
) -> tuple[AgentMessage, AgentRun]:
    now = _now()
    return (
        _new_user_message(thread, run_id, message_id, parts, metadata, message_seq, now),
        _new_active_run(
            thread, user_id, message_id, assistant_id, run_id, now, client_request_id,
            owner_id, quota_ids, skill_bindings, base_revision, target,
            write_authorized,
        ),
    )


def _new_user_message(
    thread, run_id, message_id, parts, metadata, message_seq, now
) -> AgentMessage:
    return AgentMessage(
        id=message_id, thread_id=thread.id, run_id=run_id, message_seq=message_seq,
        role="user", metadata=metadata, parts=parts, created_at=now,
    )


def _run_common_fields(
    thread, now, owner_id, quota_ids,
    skill_bindings: list[dict[str, str]] | None = None,
    base_revision=None, target=None, write_authorized: bool = False,
) -> dict:
    """活跃运行共享字段：只读、授权、基线与 owner 会话到期时间。"""
    return {
        "status": "active", "started_at": now,
        "skill_bindings": list(skill_bindings or []),
        "read_only": thread.version_id is not None or thread.mode == REVIEW_MODE,
        "write_authorized": write_authorized,
        "base_revision": base_revision, "target": target,
        "owner_id": owner_id,
        "owner_expires_at": now + _owner_delta() if owner_id else None,
        "quota_ids": quota_ids,
    }


def _new_retry_run(
    thread, message: dict, assistant_id: str, run_id: str,
    owner_id: str | None, quota_ids: tuple[str, ...],
    skill_bindings: list[dict[str, str]] | None = None,
    base_revision: int | None = None, target: ArtifactTarget | None = None,
    write_authorized: bool = False,
) -> AgentRun:
    now = _now()
    fields = _run_common_fields(
        thread, now, owner_id, quota_ids, skill_bindings, base_revision, target,
        write_authorized,
    )
    return AgentRun(
        id=run_id, thread_id=thread.id, user_id=thread.owner_id,
        user_message_id=message["id"], assistant_message_id=assistant_id,
        **fields,
    )


def _new_active_run(
    thread, user_id, message_id, assistant_id, run_id, now, client_request_id,
    owner_id, quota_ids, skill_bindings: list[dict[str, str]] | None = None,
    base_revision=None, target=None, write_authorized: bool = False,
) -> AgentRun:
    fields = _run_common_fields(
        thread, now, owner_id, quota_ids, skill_bindings, base_revision, target,
        write_authorized,
    )
    return AgentRun(
        id=run_id, thread_id=thread.id, user_id=user_id, user_message_id=message_id,
        assistant_message_id=assistant_id, client_request_id=client_request_id,
        **fields,
    )


def _run_document(run: AgentRun) -> dict:
    document = run.model_dump(by_alias=True, mode="python", exclude_none=True)
    for field, alias in _RUN_FIELDS:
        value = getattr(run, field)
        if value:
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


_RUN_FIELDS = (
    ("owner_id", "ownerId"),
    ("owner_expires_at", "ownerExpiresAt"),
    ("quota_ids", "quotaIds"),
)


def _terminal_unset() -> dict[str, str]:
    return {alias: "" for _field, alias in _RUN_FIELDS}


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


def transaction(database, callback):
    """在真实 replica set 事务中执行回调；测试替身下等价于直接调用。"""
    return _transaction(database, callback)


def claim_run_write_path(database, run_id: str, path: str, session=None) -> bool:
    """为活跃 Run 原子选择唯一正文写入路径。"""
    result = database.agent_runs.update_one(
        {"id": run_id, "status": "active", "writePath": {"$exists": False}},
        {"$set": {"writePath": path}},
        session=session,
    )
    return result.matched_count == 1


def _case_revision(database, case_id: str, session) -> int | None:
    case = database.cases.find_one({"id": case_id}, {"revision": 1}, session=session)
    return case.get("revision") if case else None


def expired_artifact_view(artifact: AgentArtifact, revision: int | None) -> AgentArtifact:
    """正文修订号已越过候选基线时，读取侧展示 expired；不回写存储状态。"""
    if (
        artifact.status == "pending" and revision is not None
        and revision != artifact.base_revision
    ):
        return artifact.model_copy(update={"status": "expired"})
    return artifact
