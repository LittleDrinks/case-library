from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_PROMPT_CHARACTERS = 100000
WORKBENCH_MODES = (
    "chat",
    "find_sources",
    "rewrite_selection",
    "rewrite_section",
    "self_check",
    "resolve_annotation",
)
REQUIRED_CONTEXT = {
    "rewrite_selection": ("selection", "section"),
    "rewrite_section": ("section",),
    "resolve_annotation": ("annotationId",),
}
FORBIDDEN_CONTEXT = {
    "chat": ("selection", "section", "annotationId"),
    "find_sources": ("selection", "section", "annotationId"),
    "rewrite_selection": ("annotationId",),
    "rewrite_section": ("selection", "annotationId"),
    "self_check": ("selection", "section", "annotationId"),
    "resolve_annotation": ("selection", "section"),
}


class AdminAISettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fallbackModel: str | None


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_total_size(self):
        if (
            sum(len(message.content) for message in self.messages)
            > MAX_PROMPT_CHARACTERS
        ):
            raise ValueError("AI 请求内容过长")
        return self


class WorkbenchSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_: int = Field(alias="from", ge=0)
    to: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=20000)

    @model_validator(mode="after")
    def validate_range(self):
        if self.to <= self.from_:
            raise ValueError("选区范围无效")
        return self


class WorkbenchSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str = Field(min_length=1, max_length=200)
    from_: int = Field(alias="from", ge=0)
    to: int = Field(ge=1)
    text: str = Field(max_length=20000)

    @model_validator(mode="after")
    def validate_range(self):
        if self.to < self.from_:
            raise ValueError("小节范围无效")
        return self


class WorkbenchContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)
    selection: WorkbenchSelection | None = None
    section: WorkbenchSection | None = None
    annotationId: str | None = Field(default=None, min_length=1, max_length=200)
    sourceScopes: list[Literal["knowledge", "platform", "web", "url"]] = Field(
        default_factory=list
    )
    urls: list[Annotated[str, Field(min_length=1, max_length=2048)]] = Field(
        default_factory=list, max_length=5
    )

    @model_validator(mode="after")
    def validate_sources(self):
        self.sourceScopes = list(dict.fromkeys(self.sourceScopes))
        if "url" in self.sourceScopes and not self.urls:
            raise ValueError("选择 url 范围时必须提供 URL")
        if "url" not in self.sourceScopes and self.urls:
            raise ValueError("未选择 url 范围时不能提供 URL")
        return self


class WorkbenchChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal[
        "chat",
        "find_sources",
        "rewrite_selection",
        "rewrite_section",
        "self_check",
        "resolve_annotation",
    ]
    instruction: str = Field(min_length=1, max_length=20000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=100)
    context: WorkbenchContext

    @model_validator(mode="after")
    def validate_mode_context(self):
        required = REQUIRED_CONTEXT.get(self.mode, ())
        values = self.context.model_dump()
        if any(values.get(field) in (None, "") for field in required):
            raise ValueError(f"{self.mode} 缺少必需上下文")
        if self.mode == "find_sources" and not self.context.sourceScopes:
            raise ValueError("find_sources 必须选择资料范围")
        forbidden = FORBIDDEN_CONTEXT.get(self.mode, ())
        if any(values.get(field) is not None for field in forbidden):
            raise ValueError(f"{self.mode} 不接受该上下文")
        return self


class WritingCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["writing_candidate"]
    text: str = Field(min_length=1, max_length=20000)
    reason: str = Field(min_length=1, max_length=2000)


class AnnotationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: str = Field(min_length=1, max_length=2000)
    section: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=4000)
    category: Literal["theory", "evidence", "teaching", "expression"]


class AnnotationCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["annotation_candidates"]
    items: list[AnnotationCandidate] = Field(min_length=1, max_length=20)


class UserAISettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["automatic", "custom"]
    baseUrl: str | None = Field(default=None, max_length=2048)
    apiKey: str | None = Field(default=None, max_length=4096)
    model: str | None = Field(default=None, max_length=200)


class ModelDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseUrl: str = Field(min_length=1, max_length=2048)
    apiKey: str = Field(min_length=1, max_length=4096)
