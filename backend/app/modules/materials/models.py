from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AccessLevel = Literal["public", "campus", "private"]
ItemStatus = Literal["queued", "running", "candidate", "duplicate", "failed"]
JobStatus = Literal["running", "succeeded", "partial_success", "failed"]


class MaterialImportItemView(BaseModel):
    id: str
    filename: str
    status: ItemStatus
    mediaType: str
    size: int
    sha256: str | None = None
    candidateId: str | None = None
    duplicateOf: str | None = None
    error: str | None = None


class MaterialImportJobView(BaseModel):
    id: str
    status: JobStatus
    accessLevel: AccessLevel
    itemCount: int
    createdBy: str
    createdAt: str
    completedAt: str | None = None
    items: list[MaterialImportItemView]


class CandidateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    title: str | None = Field(default=None, min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=4000)
    source: str | None = Field(default=None, max_length=300)
    sourceUrl: str | None = Field(default=None, max_length=2048)
    tags: list[str] | None = Field(default=None, max_length=30)
    materialType: str | None = Field(default=None, max_length=100)
    authority: str | None = Field(default=None, max_length=100)


class MaterialCandidateView(BaseModel):
    id: str
    filename: str
    mediaType: str
    size: int
    accessLevel: AccessLevel
    status: Literal["candidate", "approved", "rejected"]
    createdBy: str
    createdAt: str
    decidedAt: str | None = None
    decidedBy: str | None = None
    materialId: str | None = None


class MaterialCandidatePage(BaseModel):
    page: int
    pageSize: int
    total: int
    items: list[MaterialCandidateView]


class MaterialDetailView(BaseModel):
    id: str
    title: str
    summary: str | None = None
    excerpt: str | None = None
    source: str | None = None
    sourceUrl: str | None = None
    tags: list[str] | None = None
    publishedAt: str | None = None
    collectedAt: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
    materialType: str | None = None
    authority: str | None = None
    accessLevel: AccessLevel
    citedCount: int | None = None
    lastCitedAt: str | None = None
    filename: str | None = None
    mediaType: str | None = None
    size: int | None = None
    hasFile: bool
    contentAvailable: bool
    downloadAvailable: bool
