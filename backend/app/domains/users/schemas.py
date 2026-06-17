"""User and authentication API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginUser(BaseModel):
    id: int
    username: str
    role: str = Field(examples=["normal"])
    nickname: str = ""
    must_change_password: bool = False
    status: str = Field(default="active", examples=["active"])
    token: str = Field(
        description=(
            "HMAC-signed bearer token. This token is not a JWT and is invalidated "
            "after a successful password change or admin password reset."
        )
    )


class LoginResponse(BaseModel):
    success: bool = True
    data: LoginUser


__all__ = ["LoginResponse", "LoginUser"]
