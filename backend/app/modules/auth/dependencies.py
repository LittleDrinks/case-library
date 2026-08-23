from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request

from app.core.dependencies import get_database
from app.modules.auth.sessions import COOKIE_NAME, SessionContext, find_session


def require_session(request: Request, database=Depends(get_database)) -> SessionContext:
    context = find_session(database, request.cookies.get(COOKIE_NAME))
    if not context:
        raise HTTPException(status_code=401, detail="请先登录")
    return context


def optional_user(request: Request, database=Depends(get_database)) -> dict | None:
    context = find_session(database, request.cookies.get(COOKIE_NAME))
    return _ready_user(context) if context else None


def require_user(context: SessionContext = Depends(require_session)) -> dict:
    return _ready_user(context)


def _ready_user(context: SessionContext) -> dict:
    if context.user["must_change_password"]:
        raise HTTPException(status_code=403, detail="请先修改初始密码")
    return context.user


def require_csrf(
    request: Request, context: SessionContext = Depends(require_session)
) -> dict:
    supplied = request.headers.get("X-CSRF-Token", "")
    if not hmac.compare_digest(supplied, context.record["csrf_token"]):
        raise HTTPException(status_code=403, detail="CSRF token 无效")
    return context.record
