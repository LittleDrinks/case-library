from __future__ import annotations

from datetime import datetime
from typing import Literal

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
]
ArtifactStatus = Literal["pending", "accepted", "rejected", "expired"]
ArtifactDecision = Literal["accepted", "rejected"]


class AgentThread(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    case_id: str = Field(alias="caseId")
    owner_id: str = Field(alias="ownerId")
    version_id: str | None = Field(default=None, alias="versionId")
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
    base_revision: int | None = Field(
        default=None, alias="baseRevision", ge=1,
        description="Run 创建时锁定的案例工作版本修订号，决定与提议均以此为基线",
    )
    target: ArtifactTarget | None = Field(
        default=None,
        description="Run 创建时锁定的教师非空选区；无选区不自动锁定全文",
    )
    resources: list[dict[str, str]] = Field(default_factory=list)
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

    kind: Literal["case", "knowledge", "material"]
    id: str
    title: str
    snippet: str = ""


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
    base_revision: int = Field(alias="baseRevision", ge=1)
    target: ArtifactTarget
    replacement: str
    reason: str = ""
    sources: list[SourceRef] = Field(default_factory=list)
    decided_by: str | None = Field(default=None, alias="decidedBy")
    decided_at: datetime | None = Field(default=None, alias="decidedAt")
    created_at: datetime = Field(alias="createdAt")


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
    runs: list[AgentRun] = Field(default_factory=list)
    active_run: AgentRun | None = Field(default=None, alias="activeRun")
    latest_run: AgentRun | None = Field(default=None, alias="latestRun")
