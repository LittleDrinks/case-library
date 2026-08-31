from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MessageRole = Literal["user", "assistant"]
RunStatus = Literal["active", "completed", "failed", "cancelled"]
TerminalRunStatus = Literal["completed", "failed", "cancelled"]


class AgentThread(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    case_id: str = Field(alias="caseId")
    owner_id: str = Field(alias="ownerId")
    is_default: bool = Field(alias="isDefault")
    next_message_seq: int = Field(default=0, alias="nextMessageSeq")
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
    status: RunStatus
    started_at: datetime = Field(alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")
    error: str | None = None


class AgentSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    case_id: str = Field(alias="caseId")
    messages: list[AgentMessage]
    active_run: AgentRun | None = Field(default=None, alias="activeRun")
    latest_run: AgentRun | None = Field(default=None, alias="latestRun")
