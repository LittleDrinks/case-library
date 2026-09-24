from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    from_: int = Field(alias="from", ge=0)
    to: int = Field(ge=0)
    revision: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_anchor(self) -> "AnnotationCreate":
        if not self.quote.strip():
            raise ValueError("批注引用不能为空")
        if self.from_ >= self.to:
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
    revision: int = Field(ge=1)
    status: AnnotationStatus
    anchorState: AnchorState | None = None
    replies: list[AnnotationReplyView]
    revisions: list[AnnotationRevisionView] | None = None
    restoredFromId: str | None = None
    createdBy: str
    createdAt: str
