"""AI prompt and review API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

JsonDict = dict[str, Any]


class PromptMetadata(BaseModel):
    id: str
    category: str
    name: str
    description: str = ""
    variables: list[str] = []
    output_schema: str | None = None


class PromptListResponse(BaseModel):
    success: bool = True
    data: list[PromptMetadata]


class AIChatRequest(BaseModel):
    prompt_id: str = Field(description="Prompt identifier returned by GET /api/prompts.")
    variables: JsonDict = Field(default_factory=dict)
    model: str | None = Field(default=None, description="Optional model name from AI_MODELS.")


class AIChatResponse(BaseModel):
    success: bool = True
    answer: str
    parsed: JsonDict | list[Any] | str | int | float | bool | None = None
    parse_error: str | None = None


__all__ = [
    "AIChatRequest",
    "AIChatResponse",
    "JsonDict",
    "PromptListResponse",
    "PromptMetadata",
]
