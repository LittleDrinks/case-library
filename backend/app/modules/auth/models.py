from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currentPassword: str
    newPassword: str


class UserView(BaseModel):
    id: str
    username: str
    name: str
    role: str
    mustChangePassword: bool


class SessionView(BaseModel):
    user: UserView
    csrfToken: str
