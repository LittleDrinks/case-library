#!/usr/bin/env python3
"""Shared FastAPI dependencies and compatibility call sites."""

import sys

from ai_client import call_chat_completion as _call_chat_completion
from database import get_case
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from security import get_case_owner_username, get_current_user

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Use `Authorization: Bearer <token>` with the login token.",
)


BearerCredentials = HTTPAuthorizationCredentials | None
OptionalBearer = Depends(bearer_scheme)
RequiredBearer = Depends(bearer_scheme)


def require_current_user(request: Request) -> dict:
    current_user = get_current_user(dict(request.headers))
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")
    return current_user


def ensure_case_history_visible(case_id: int, current_user: dict | None) -> dict:
    case = get_case(case_id, include_deleted=True)
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    is_admin = bool(current_user and current_user.get("role") == "admin")
    is_owner = bool(current_user and current_user.get("username") == get_case_owner_username(case))
    if is_admin or is_owner:
        return case
    raise HTTPException(status_code=403, detail="无权查看该案例的历史记录")


def call_chat_completion(prompt_text, model, settings=None, *, system_content=""):
    main_module = sys.modules.get("main")
    main_call = getattr(main_module, "call_chat_completion", None)
    if main_call and main_call is not _call_chat_completion:
        return main_call(prompt_text, model, settings=settings, system_content=system_content)
    return _call_chat_completion(prompt_text, model, settings=settings, system_content=system_content)
