from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.core.dependencies import get_database
from app.modules.auth.dependencies import require_admin, require_csrf
from app.modules.auth.management_service import (
    AccountManagementError,
    AccountManagementService,
)
from app.modules.auth.models import CredentialPassword, Username

Reason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]

router = APIRouter(prefix="/api/admin", tags=["admin-accounts"])


class ManagedAccountView(BaseModel):
    id: str
    username: str
    role: str
    mustChangePassword: bool


class ManagedAccountList(BaseModel):
    items: list[ManagedAccountView]
    total: int
    page: int
    pageSize: int


class OpenAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username
    temporaryPassword: CredentialPassword
    reason: Reason


class TemporaryPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temporaryPassword: CredentialPassword
    reason: Reason


class AccountOperationResult(BaseModel):
    account: ManagedAccountView
    revokedSessions: int


class AccountOperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason


class AccountOperationView(BaseModel):
    id: str
    actorId: str
    actorUsername: str
    targetId: str | None
    targetUsername: str | None
    action: str
    createdAt: str
    reason: str
    result: str
    detail: str


class AccountOperationList(BaseModel):
    items: list[AccountOperationView]
    total: int
    page: int
    pageSize: int


@router.get("/accounts", response_model=ManagedAccountList)
def list_accounts(
    query: Annotated[str, Query(alias="q", max_length=80)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
    database=Depends(get_database),
    _admin: dict = Depends(require_admin),
):
    return AccountManagementService(database).list_accounts(query, page, page_size)


@router.get("/account-operations", response_model=AccountOperationList)
def list_account_operations(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
    database=Depends(get_database),
    _admin: dict = Depends(require_admin),
):
    return AccountManagementService(database).list_operations(page, page_size)


@router.post("/accounts", status_code=201, response_model=ManagedAccountView)
def open_account(
    body: OpenAccountRequest,
    database=Depends(get_database),
    admin: dict = Depends(require_admin),
    _csrf: dict = Depends(require_csrf),
):
    try:
        return AccountManagementService(database).open_account(
            admin, body.username, body.temporaryPassword, body.reason
        )
    except AccountManagementError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post(
    "/accounts/{account_id}/temporary-password",
    response_model=ManagedAccountView,
)
def reset_temporary_password(
    account_id: str,
    body: TemporaryPasswordRequest,
    database=Depends(get_database),
    admin: dict = Depends(require_admin),
    _csrf: dict = Depends(require_csrf),
):
    try:
        return AccountManagementService(database).reset_temporary_password(
            admin, account_id, body.temporaryPassword, body.reason
        )
    except AccountManagementError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post(
    "/accounts/{account_id}/force-logout",
    response_model=AccountOperationResult,
)
def force_logout(
    account_id: str,
    body: AccountOperationRequest,
    database=Depends(get_database),
    admin: dict = Depends(require_admin),
    _csrf: dict = Depends(require_csrf),
):
    try:
        return AccountManagementService(database).force_logout(
            admin, account_id, body.reason
        )
    except AccountManagementError as error:
        raise HTTPException(error.status_code, error.detail) from error
