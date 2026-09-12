from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

AnnotationSource = Literal["manual", "selfcheck", "ai", "admin"]
AnnotationStatus = Literal["pending", "resolved"]
AnchorState = Literal["active", "changed", "deleted"]
AnnotationRevisionStatus = Literal["pending", "accepted", "rejected", "expired"]


class AnnotationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    quote: str = Field(min_length=1, max_length=2000)
    section: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=4000)
    source: AnnotationSource = "manual"
    from_: int | None = Field(default=None, alias="from", ge=0)
    to: int | None = Field(default=None, ge=0)
    quoteHash: str | None = Field(
        default=None,
        alias="quoteHash",
        validation_alias=AliasChoices("quoteHash", "hash"),
        max_length=128,
    )
    revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_manual_anchor(self) -> "AnnotationCreate":
        if not self.quote.strip():
            raise ValueError("批注引用不能为空")
        anchor = (self.from_, self.to, self.quoteHash, self.revision)
        if self.source == "manual" and any(value is None for value in anchor):
            raise ValueError("手动批注必须提供当前正文锚点")
        if any(value is not None for value in anchor) and any(value is None for value in anchor):
            raise ValueError("批注锚点字段不完整")
        if self.from_ is not None and self.to is not None and self.from_ >= self.to:
            raise ValueError("批注锚点范围无效")
        return self


class AnnotationReplyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)


class AnnotationStatusPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AnnotationStatus


class AnnotationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)


class AnnotationReplyView(AnnotationReplyCreate):
    id: str
    createdBy: str
    createdAt: str


class AnnotationRevisionView(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    artifactId: str
    runId: str
    baseRevision: int = Field(ge=1)
    target: dict
    replacement: str
    reason: str
    status: AnnotationRevisionStatus
    createdBy: str
    createdAt: str


class AnnotationView(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    caseId: str
    versionId: str | None = None
    quote: str
    section: str
    content: str
    source: AnnotationSource
    from_: int | None = Field(default=None, alias="from", ge=0)
    to: int | None = Field(default=None, ge=0)
    quoteHash: str | None = Field(default=None, alias="quoteHash")
    revision: int | None = Field(default=None, ge=1)
    status: AnnotationStatus
    anchorState: AnchorState | None = None
    replies: list[AnnotationReplyView]
    revisions: list[AnnotationRevisionView] | None = None
    restoredFromId: str | None = None
    createdBy: str
    createdAt: str
