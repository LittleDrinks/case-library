from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.core.dependencies import get_database
from app.modules.auth.dependencies import require_admin, require_csrf, require_user
from app.modules.auth.management_service import (
    AccountManagementError,
    AccountManagementService,
)

ApplicantName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
StudentNumber = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
]

router = APIRouter(tags=["campus-access"])
Reason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class CampusApplicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applicantName: ApplicantName
    studentNumber: StudentNumber


class CampusApplicationDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    reason: Reason


class CampusApplicationOperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason


class CampusApplicationHistoryView(BaseModel):
    id: str
    actorUsername: str
    action: str
    createdAt: str
    reason: str
    result: str
    detail: str


class CampusApplicationView(BaseModel):
    id: str
    applicantName: str
    studentNumber: str
    identitySource: Literal["self_reported"]
    status: Literal["pending", "approved", "rejected", "revoked"]
    submittedAt: str
    history: list[CampusApplicationHistoryView]


class AdminCampusApplicationView(CampusApplicationView):
    userId: str
    username: str


class CampusAccessStatusView(BaseModel):
    campusVerified: bool
    grantSource: Literal["legacy", "application"] | None
    currentStatus: Literal[
        "not_applied", "pending", "approved", "rejected", "revoked"
    ]
    applications: list[CampusApplicationView]


class AdminCampusApplicationList(BaseModel):
    items: list[AdminCampusApplicationView]
    total: int
    page: int
    pageSize: int


class LegacyCampusGrantView(BaseModel):
    userId: str
    username: str
    role: Literal["admin", "user"]
    grantSource: Literal["legacy"]


class LegacyCampusGrantList(BaseModel):
    items: list[LegacyCampusGrantView]
    total: int
    page: int
    pageSize: int


class LegacyCampusGrantRevokeView(BaseModel):
    userId: str
    username: str
    campusVerified: bool
    grantSource: Literal["legacy"]
    revokedAt: str


@router.get("/api/auth/campus-access", response_model=CampusAccessStatusView)
def campus_access_status(
    database=Depends(get_database), user: dict = Depends(require_user)
):
    return AccountManagementService(database).campus_access_status(user)


@router.post(
    "/api/auth/campus-access/applications",
    status_code=201,
    response_model=CampusApplicationView,
)
def submit_campus_application(
    body: CampusApplicationRequest,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _csrf: dict = Depends(require_csrf),
):
    try:
        return AccountManagementService(database).submit_campus_application(
            user, body.applicantName, body.studentNumber
        )
    except AccountManagementError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get(
    "/api/admin/campus-access-applications",
    response_model=AdminCampusApplicationList,
)
def list_campus_access_applications(
    query: Annotated[str, Query(alias="q", max_length=80)] = "",
    status: Literal["pending", "approved", "rejected", "revoked", "all"] = "pending",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
    database=Depends(get_database),
    _admin: dict = Depends(require_admin),
):
    return AccountManagementService(database).list_campus_access_applications(
        query, None if status == "all" else status, page, page_size
    )


@router.get(
    "/api/admin/campus-access-legacy-grants",
    response_model=LegacyCampusGrantList,
)
def list_legacy_campus_grants(
    query: Annotated[str, Query(alias="q", max_length=80)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
    database=Depends(get_database),
    _admin: dict = Depends(require_admin),
):
    return AccountManagementService(database).list_legacy_campus_grants(
        query, page, page_size
    )


@router.post(
    "/api/admin/campus-access-users/{user_id}/revoke-legacy",
    response_model=LegacyCampusGrantRevokeView,
)
def revoke_legacy_campus_access(
    user_id: str,
    body: CampusApplicationOperationRequest,
    database=Depends(get_database),
    admin: dict = Depends(require_admin),
    _csrf: dict = Depends(require_csrf),
):
    try:
        return AccountManagementService(database).revoke_legacy_campus_access(
            admin, user_id, body.reason
        )
    except AccountManagementError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post(
    "/api/admin/campus-access-applications/{application_id}/decision",
    response_model=AdminCampusApplicationView,
)
def decide_campus_access_application(
    application_id: str,
    body: CampusApplicationDecisionRequest,
    database=Depends(get_database),
    admin: dict = Depends(require_admin),
    _csrf: dict = Depends(require_csrf),
):
    try:
        return AccountManagementService(database).decide_campus_application(
            admin, application_id, body.decision, body.reason
        )
    except AccountManagementError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post(
    "/api/admin/campus-access-applications/{application_id}/revoke",
    response_model=AdminCampusApplicationView,
)
def revoke_campus_access_application(
    application_id: str,
    body: CampusApplicationOperationRequest,
    database=Depends(get_database),
    admin: dict = Depends(require_admin),
    _csrf: dict = Depends(require_csrf),
):
    try:
        return AccountManagementService(database).revoke_campus_access(
            admin, application_id, body.reason
        )
    except AccountManagementError as error:
        raise HTTPException(error.status_code, error.detail) from error
