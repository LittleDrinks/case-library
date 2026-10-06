from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.config import Settings
from app.core.dependencies import get_database, get_settings
from app.modules.auth.dependencies import require_csrf, require_session
from app.modules.auth.models import (
    ChangePasswordRequest,
    LoginRequest,
    RegistrationRequest,
    SessionView,
    UserView,
)
from app.modules.auth.service import (
    PasswordChangeError,
    RegistrationError,
    authenticate,
    change_password,
    register_user,
    user_view,
)
from app.modules.auth.sessions import (
    COOKIE_NAME,
    SessionContext,
    create_session,
    delete_session,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _session_payload(context: SessionContext) -> dict:
    return {
        "user": user_view(context.user),
        "csrfToken": context.record["csrf_token"],
    }


def _set_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )


@router.post("/register", status_code=201, response_model=UserView)
def register(body: RegistrationRequest, database=Depends(get_database)):
    try:
        user = register_user(database, body.username, body.password)
    except RegistrationError as error:
        raise HTTPException(error.status_code, error.detail) from error
    return user_view(user)


@router.post("/login", response_model=SessionView)
def login(
    body: LoginRequest,
    response: Response,
    database=Depends(get_database),
    settings: Settings = Depends(get_settings),
):
    user = authenticate(database, body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token, context = create_session(database, user, settings.session_ttl_seconds)
    _set_cookie(response, token, settings)
    return _session_payload(context)


@router.get("/session", response_model=SessionView)
def session(context: SessionContext = Depends(require_session)):
    return _session_payload(context)


@router.post("/change-password", status_code=204)
def update_password(
    body: ChangePasswordRequest,
    response: Response,
    database=Depends(get_database),
    record: dict = Depends(require_csrf),
):
    try:
        change_password(
            database, record["user_id"], body.currentPassword, body.newPassword
        )
    except PasswordChangeError as error:
        raise HTTPException(error.status_code, error.detail) from error
    response.delete_cookie(COOKIE_NAME, path="/")
    response.status_code = 204
    return response


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    database=Depends(get_database),
    _session: dict = Depends(require_csrf),
):
    delete_session(database, request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path="/")
