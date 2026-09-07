from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CaseSourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sourceCaseId: str = Field(min_length=1, max_length=100)
    versionId: str | None = Field(default=None, min_length=1, max_length=100)
    revision: int = Field(ge=1)


class CaseSourceView(BaseModel):
    id: str
    sourceType: Literal["case"]
    caseId: str
    versionId: str
    versionNumber: int
    title: str
    sourceUrl: str
    publishedAt: str | None = None
    contentAvailable: bool
    createdAt: str
