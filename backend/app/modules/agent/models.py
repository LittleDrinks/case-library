from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


MessageRole = Literal["user", "assistant"]
RunStatus = Literal["active", "completed", "failed", "cancelled"]
TerminalRunStatus = Literal["completed", "failed", "cancelled"]
ThreadEventType = Literal[
    "message.created",
    "run.started",
    "run.completed",
    "run.failed",
    "run.cancelled",
    "artifact.created",
    "artifact.decided",
    "version.created",
    "document.written",
    "document.undone",
]
ArtifactStatus = Literal["pending", "accepted", "rejected", "expired"]
ArtifactDecision = Literal["accepted", "rejected"]
ArtifactKind = Literal["range", "document"]
WriteStatus = Literal["written", "undone"]
SourceKind = Literal["case", "knowledge", "material", "attachment"]

# 管理员审核对话：绑定当前待审工作稿、服务端全链路只读、按管理员私人隔离。
REVIEW_MODE = "review"


class AgentThread(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    case_id: str = Field(alias="caseId")
    owner_id: str = Field(alias="ownerId")
    version_id: str | None = Field(default=None, alias="versionId")
    mode: str | None = None
    title: str | None = None
    is_default: bool = Field(alias="isDefault")
    next_message_seq: int = Field(default=0, alias="nextMessageSeq")
    event_seq: int = Field(default=0, alias="eventSeq")
    active_run_id: str | None = Field(default=None, alias="activeRunId")
    last_run_id: str | None = Field(default=None, alias="lastRunId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")


class AgentMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    thread_id: str = Field(alias="threadId")
    run_id: str = Field(alias="runId")
    message_seq: int = Field(default=0, alias="messageSeq")
    role: MessageRole
    metadata: dict[str, object] = Field(default_factory=dict)
    parts: list[dict[str, object]]
    created_at: datetime = Field(alias="createdAt")


class AgentRun(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    thread_id: str = Field(alias="threadId")
    user_id: str = Field(alias="userId")
    user_message_id: str = Field(alias="userMessageId")
    assistant_message_id: str = Field(alias="assistantMessageId")
    client_request_id: str | None = Field(default=None, alias="clientRequestId")
    status: RunStatus
    skill_bindings: list[dict[str, str]] = Field(
        default_factory=list, alias="skillBindings",
        description="Run 创建时固化的已发布 Skill 版本凭据，失败/取消仍保留",
    )
    read_only: bool = Field(default=False, alias="readOnly")
    write_authorized: bool = Field(
        default=False, alias="writeAuthorized",
        description="Run 创建时由服务端从教师当前消息文本判定的直接写入授权，"
                    "不来自工具参数或模型自报",
    )
    base_revision: int | None = Field(
        default=None, alias="baseRevision", ge=1,
        description="Run 创建时锁定的案例工作版本修订号，决定与提议均以此为基线",
    )
    target: ArtifactTarget | None = Field(
        default=None,
        description="Run 创建时锁定的教师非空选区；无选区不自动锁定全文",
    )
    annotation_id: str | None = Field(default=None, alias="annotationId")
    write_path: Literal["document", "direct_write"] | None = Field(
        default=None, alias="writePath", exclude=True,
    )
    resources: list[dict[str, str]] = Field(default_factory=list)
    tool_timings: dict[str, dict[str, str]] = Field(default_factory=dict, alias="toolTimings")
    started_at: datetime = Field(alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")
    error: str | None = None
    cancel_requested_at: datetime | None = Field(
        default=None, alias="cancelRequestedAt", exclude=True
    )
    owner_id: str | None = Field(default=None, alias="ownerId", exclude=True)
    owner_expires_at: datetime | None = Field(default=None, alias="ownerExpiresAt", exclude=True)
    quota_ids: tuple[str, ...] = Field(default_factory=tuple, alias="quotaIds", exclude=True)


class SourceRef(BaseModel):
    """服务端从工具实际结果重建的来源引用，模型输出不能伪造。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: SourceKind
    id: str
    title: str
    snippet: str = ""
    version: str | None = None
    version_id: str | None = Field(default=None, alias="versionId")
    source_case_id: str | None = Field(
        default=None, alias="sourceCaseId",
        description="kind=case 时的真实案例 ID；id 可能是资料区挂载条目 ID",
    )
    location: str | None = None

    def identity(self) -> tuple[str, str, str]:
        return (self.kind, self.id, self.version_id or self.version or "")


class ArtifactTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_pos: int = Field(alias="from", ge=0)
    to_pos: int = Field(alias="to", ge=0)
    quote: str


class AgentArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    case_id: str = Field(alias="caseId")
    thread_id: str = Field(alias="threadId")
    run_id: str = Field(alias="runId")
    status: ArtifactStatus = "pending"
    kind: ArtifactKind = "range"
    base_revision: int = Field(alias="baseRevision", ge=1)
    target: ArtifactTarget
    annotation_id: str | None = Field(default=None, alias="annotationId")
    replacement: str
    blocks: list[dict[str, object]] = Field(default_factory=list)
    reason: str = ""
    sources: list[SourceRef] = Field(default_factory=list)
    decided_by: str | None = Field(default=None, alias="decidedBy")
    decided_at: datetime | None = Field(default=None, alias="decidedAt")
    created_at: datetime = Field(alias="createdAt")


class AgentWrite(BaseModel):
    """显式直接写入的落地记录：恰好一次写正文，保留撤销所需的前后文档。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    case_id: str = Field(alias="caseId")
    thread_id: str = Field(alias="threadId")
    run_id: str = Field(alias="runId")
    status: WriteStatus = "written"
    scope: Literal["document", "selection"]
    summary: str = ""
    blocks: list[dict[str, object]] = Field(default_factory=list)
    before_document: dict[str, object] = Field(alias="beforeDocument")
    document: dict[str, object]
    document_steps: list[dict[str, Any]] = Field(default_factory=list, alias="documentSteps")
    base_revision: int = Field(alias="baseRevision", ge=1)
    result_revision: int = Field(alias="resultRevision", ge=1)
    created_by: str = Field(alias="createdBy")
    created_at: datetime = Field(alias="createdAt")
    undone_by: str | None = Field(default=None, alias="undoneBy")
    undone_at: datetime | None = Field(default=None, alias="undoneAt")


class AgentWriteView(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    run_id: str = Field(alias="runId")
    scope: Literal["document", "selection"]
    summary: str = ""
    status: WriteStatus
    revision: int = Field(ge=1)


def write_view(write: dict) -> dict:
    """对外暴露的写入记录视图：不含文档内容，只含撤销回显所需字段。"""
    return {
        "id": write["id"], "runId": write["runId"], "scope": write["scope"],
        "summary": write.get("summary", ""), "status": write["status"],
        "revision": write["resultRevision"],
    }


class AgentThreadEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    thread_id: str = Field(alias="threadId")
    event_seq: int = Field(alias="eventSeq")
    event_type: ThreadEventType = Field(alias="type")
    run_id: str = Field(alias="runId")
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(alias="createdAt")


class AgentThreadSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    version_id: str | None = Field(default=None, alias="versionId")
    title: str | None = None
    is_default: bool = Field(alias="isDefault")
    running: bool = False
    event_seq: int = Field(default=0, alias="eventSeq")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")


class AgentSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    case_id: str = Field(alias="caseId")
    version_id: str | None = Field(default=None, alias="versionId")
    title: str | None = None
    event_seq: int = Field(default=0, alias="eventSeq")
    messages: list[AgentMessage]
    artifacts: list[AgentArtifact] = Field(default_factory=list)
    writes: list[AgentWriteView] = Field(default_factory=list)
    runs: list[AgentRun] = Field(default_factory=list)
    active_run: AgentRun | None = Field(default=None, alias="activeRun")
    latest_run: AgentRun | None = Field(default=None, alias="latestRun")
