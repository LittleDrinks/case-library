from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

Username = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
]
CredentialPassword = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128),
]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username
    password: CredentialPassword


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username
    password: CredentialPassword


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
    campusVerified: bool = False


class SessionView(BaseModel):
    user: UserView
    csrfToken: str
