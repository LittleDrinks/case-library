from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AdminAISettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fallbackModel: str | None


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
