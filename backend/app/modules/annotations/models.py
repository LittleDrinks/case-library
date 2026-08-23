from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AnnotationSource = Literal["selfcheck", "ai", "admin"]
AnnotationStatus = Literal["pending", "resolved"]


class AnnotationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: str = Field(min_length=1, max_length=2000)
    section: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=4000)
    source: AnnotationSource


class AnnotationReplyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)


class AnnotationStatusPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AnnotationStatus


class AnnotationReplyView(AnnotationReplyCreate):
    id: str
    createdBy: str
    createdAt: str


class AnnotationView(AnnotationCreate):
    id: str
    caseId: str
    versionId: str
    status: AnnotationStatus
    replies: list[AnnotationReplyView]
    createdBy: str
    createdAt: str
