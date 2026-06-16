#!/usr/bin/env python3
"""Authentication routes."""

from database import authenticate_user, change_user_password
from fastapi import APIRouter, Form, HTTPException
from schemas import LoginResponse, SuccessMessageResponse
from security import create_auth_token

router = APIRouter()


@router.post(
    "/api/auth/login",
    response_model=LoginResponse,
    summary="Login and receive a bearer token",
    description=(
        "Authenticate with form credentials. The returned `data.token` must be sent as "
        "`Authorization: Bearer <token>` on protected endpoints."
    ),
)
async def login(username: str = Form(...), password: str = Form(...)):
    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_auth_token(user["username"], user.get("token_version", 0))
    return {
        "success": True,
        "data": {
            "id": user["id"],
            "username": user["username"],
            "role": user.get("role", "normal"),
            "nickname": user.get("nickname", ""),
            "must_change_password": bool(user.get("must_change_password", False)),
            "status": user.get("status", "active"),
            "token": token,
        },
    }


@router.post(
    "/api/auth/change-password",
    response_model=SuccessMessageResponse,
    summary="Change a user's password",
    description=(
        "Change a password by providing the username, old password, and new password. "
        "Existing bearer tokens for the user are invalidated after a successful change."
    ),
)
async def change_password(
    username: str = Form(...),
    old_password: str = Form(...),
    new_password: str = Form(...),
):
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="新密码长度不能少于8位")
    if not change_user_password(username, old_password, new_password):
        raise HTTPException(status_code=400, detail="用户名或原密码错误")
    return {"success": True, "message": "密码修改成功"}
