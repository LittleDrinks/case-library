from __future__ import annotations

import secrets
from datetime import UTC, datetime

from pymongo import DESCENDING, ReturnDocument
from pymongo.database import Database

CASE_METADATA_FIELDS = (
    "typeId",
    "typeName",
    "course",
    "author",
    "organization",
    "stageText",
    "audience",
    "purpose",
    "theoryPoints",
    "citations",
    "kit",
    "likes",
)
CASE_VIEW_FIELDS = (
    "id",
    "title",
    "summary",
    "document",
    "revision",
    "workflowStatus",
    "publicationStatus",
    "submittedVersionId",
    "publishedVersionId",
    "versionNumber",
    "ownerId",
    "createdAt",
    "updatedAt",
    "submittedAt",
    "publishedAt",
    *CASE_METADATA_FIELDS,
)
CASE_CARD_FIELDS = (
    "id",
    "title",
    "summary",
    "workflowStatus",
    "publicationStatus",
    "createdAt",
    "updatedAt",
    "publishedAt",
    "typeId",
    "typeName",
    "course",
    "author",
    "organization",
    "stageText",
    "audience",
    "purpose",
    "likes",
    "theoryPoints",
)


class CaseError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


class RevisionConflict(CaseError):
    def __init__(self, current_revision: int):
        super().__init__(409, "案例已在其他位置更新")
        self.current_revision = current_revision


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _can_read(case: dict, user: dict | None) -> bool:
    return case["publicationStatus"] == "public" or _is_internal(case, user)


def _is_internal(case: dict, user: dict | None) -> bool:
    return bool(user and (user["role"] == "admin" or case["ownerId"] == user["id"]))


def _can_write(case: dict, user: dict) -> bool:
    return case["ownerId"] == user["id"]


def case_metadata(case: dict) -> dict:
    return {key: case.get(key) for key in CASE_METADATA_FIELDS}


def case_view(case: dict) -> dict:
    return {key: case.get(key) for key in CASE_VIEW_FIELDS}


def case_card(case: dict, include_owner: bool = False) -> dict:
    view = {key: case.get(key) for key in CASE_CARD_FIELDS}
    if include_owner:
        view["ownerId"] = case.get("ownerId")
    return view


def get_case(database: Database, case_id: str, user: dict | None) -> dict:
    case = database.cases.find_one({"id": case_id})
    if not case or not _can_read(case, user):
        raise CaseError(404, "案例不存在")
    return _reader_view(database, case, user)


def get_public_case(database: Database, case_id: str) -> dict:
    case = database.cases.find_one({"id": case_id})
    if not case:
        raise CaseError(404, "案例不存在")
    from app.modules.cases.published import PublishedCaseReader

    return PublishedCaseReader(database).get(case)


def _reader_view(database: Database, case: dict, user: dict | None) -> dict:
    if _is_internal(case, user):
        return case_view(case)
    from app.modules.cases.published import PublishedCaseReader

    return PublishedCaseReader(database).get(case)


def list_cases(database: Database, user: dict | None, scope: str) -> list[dict]:
    if scope == "public":
        return _list_public_cases(database)
    if scope == "admin":
        return _list_admin_cases(database, user)
    return _list_my_cases(database, user)


def _list_public_cases(database: Database) -> list[dict]:
    rows = database.cases.find({"publicationStatus": "public"}).sort(
        "publishedAt", DESCENDING
    )
    return [case_card(_reader_view(database, case, None)) for case in rows]


def _list_my_cases(database: Database, user: dict | None) -> list[dict]:
    if not user:
        raise CaseError(401, "请先登录")
    rows = database.cases.find({"ownerId": user["id"]}).sort("updatedAt", DESCENDING)
    return [case_card(case, include_owner=True) for case in rows]


def _list_admin_cases(database: Database, user: dict | None) -> list[dict]:
    if not user or user["role"] != "admin":
        raise CaseError(403, "仅管理员可查看管理队列")
    rows = database.cases.find({}).sort("updatedAt", DESCENDING)
    return [case_card(case, include_owner=True) for case in rows]


def create_case(database: Database, body: dict, user: dict) -> dict:
    now = _now()
    case = {
        "id": f"c-{secrets.token_hex(6)}",
        "title": body["title"],
        "summary": "",
        "document": body["document"],
        "revision": 1,
        "workflowStatus": "draft",
        "publicationStatus": "none",
        "versionNumber": 0,
        "ownerId": user["id"],
        "createdAt": now,
        "updatedAt": now,
    }
    database.cases.insert_one(case)
    return case_view(case)


def update_case(database: Database, case_id: str, body: dict, user: dict) -> dict:
    current = database.cases.find_one({"id": case_id})
    if not current:
        raise CaseError(404, "案例不存在")
    if not _can_write(current, user):
        raise CaseError(403, "无权编辑该案例")
    if current["workflowStatus"] != "draft":
        raise CaseError(409, "案例当前不可编辑")
    return _cas_update(database, case_id, body)


def _cas_update(database: Database, case_id: str, body: dict) -> dict:
    changes = {
        key: body[key] for key in ("title", "document") if body.get(key) is not None
    }
    changes["updatedAt"] = _now()
    updated = database.cases.find_one_and_update(
        {"id": case_id, "revision": body["revision"]},
        {"$set": changes, "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if updated:
        return case_view(updated)
    current = database.cases.find_one({"id": case_id})
    raise RevisionConflict(current["revision"])
