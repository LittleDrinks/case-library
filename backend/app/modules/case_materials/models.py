from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CaseMaterialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    materialId: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1)


class CaseMaterialView(BaseModel):
    id: str
    title: str
    accessLevel: str
    contentAvailable: bool
    summary: str | None = None
    source: str | None = None
    sourceUrl: str | None = None
    tags: list[str] | None = None
    materialType: str | None = None
    authority: str | None = None
    filename: str | None = None
    mediaType: str | None = None
    size: int | None = None
    hasFile: bool
