from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_PROMPT_CHARACTERS = 100000


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
