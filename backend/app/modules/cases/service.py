from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime

from pymongo import DESCENDING, ReturnDocument
from pymongo.database import Database

from app.modules.cases.actions import available_actions
from app.modules.cases.document_schema import citation_refs

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
    "tagIds",
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
    "tagIds",
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


def run_transaction(database: Database, callback):
    with database.client.start_session() as session:
        return session.with_transaction(callback)


def advance_revision(database, case_id: str, user: dict, revision: int, session) -> None:
    query = {"id": case_id, "ownerId": user["id"], "workflowStatus": "draft", "revision": revision}
    updated = database.cases.find_one_and_update(
        query,
        {"$set": {"updatedAt": _now()}, "$inc": {"revision": 1}},
        session=session,
        return_document=ReturnDocument.AFTER,
    )
    if updated:
        return
    current = database.cases.find_one({"id": case_id}, session=session)
    if not current:
        raise CaseError(404, "案例不存在")
    if current["ownerId"] != user["id"]:
        raise CaseError(403, "仅案例作者可编辑案例")
    if current["workflowStatus"] != "draft":
        raise CaseError(409, "案例当前不可编辑")
    raise RevisionConflict(current["revision"])


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


def case_card(case: dict, include_owner: bool = False, user: dict | None = None) -> dict:
    view = {key: case.get(key) for key in CASE_CARD_FIELDS}
    if include_owner:
        view["ownerId"] = case.get("ownerId")
    view["availableActions"] = available_actions(case, user)
    return view


def internal_case_view(case: dict, user: dict) -> dict:
    """内部案例视图唯一权威序列化：动作资格实时计算，lastReview 仅作者可见。"""
    view = case_view(case)
    if user["id"] == case.get("ownerId"):
        view["lastReview"] = case.get("lastReview")
    view["availableActions"] = available_actions(case, user)
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
        return internal_case_view(case, user)
    from app.modules.cases.published import PublishedCaseReader

    return PublishedCaseReader(database).get(case)


def list_cases(database: Database, user: dict | None, scope: str) -> list[dict]:
    if scope == "public":
        return _list_public_cases(database)
    if scope == "admin":
        return _list_admin_cases(database, user)
    return _list_my_cases(database, user)


DRAFT_PAGE_FIELDS = ("id", "title", "updatedAt")
DRAFT_PAGE_MAX_SIZE = 50


def list_drafts(
    database: Database, user: dict, query: str, page: int, page_size: int
) -> dict:
    """加入来源弹窗的本人可编辑草稿分页：只出 id/标题/更新时间，支持标题检索。"""
    condition: dict = {"ownerId": user["id"], "workflowStatus": "draft"}
    keyword = query.strip()
    if keyword:
        condition["title"] = {"$regex": re.escape(keyword), "$options": "i"}
    total = database.cases.count_documents(condition)
    rows = (
        database.cases.find(
            condition, {**{field: 1 for field in DRAFT_PAGE_FIELDS}, "_id": 0}
        )
        .sort("updatedAt", DESCENDING)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = [{field: row.get(field) for field in DRAFT_PAGE_FIELDS} for row in rows]
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


def _list_public_cases(database: Database) -> list[dict]:
    rows = database.cases.find({"publicationStatus": "public"}).sort(
        "publishedAt", DESCENDING
    )
    return [case_card(_reader_view(database, case, None)) for case in rows]


def _pending_annotation_count(database: Database, last_review: dict | None) -> int:
    ids = (last_review or {}).get("annotationIds") or []
    if not ids:
        return 0
    query = {"id": {"$in": ids}, "status": "pending"}
    return database.annotations.count_documents(query)


def _my_case_card(database: Database, case: dict, user: dict) -> dict:
    """作者自己的卡片：退回意见与待处理批注仅在此列表可见，公开视图不带。"""
    card = case_card(case, include_owner=True, user=user)
    last_review = case.get("lastReview")
    card["lastReview"] = last_review
    card["pendingAnnotationCount"] = _pending_annotation_count(database, last_review)
    return card


def _list_my_cases(database: Database, user: dict | None) -> list[dict]:
    if not user:
        raise CaseError(401, "请先登录")
    rows = database.cases.find({"ownerId": user["id"]}).sort("updatedAt", DESCENDING)
    return [_my_case_card(database, case, user) for case in rows]


def _list_admin_cases(database: Database, user: dict | None) -> list[dict]:
    if not user or user["role"] != "admin":
        raise CaseError(403, "仅管理员可查看管理队列")
    rows = database.cases.find({}).sort("updatedAt", DESCENDING)
    return [case_card(case, include_owner=True, user=user) for case in rows]


def create_case(database: Database, body: dict, user: dict) -> dict:
    if citation_refs(body["document"]):
        raise CaseError(422, "正文引用的来源不在资料区")
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
    return internal_case_view(case, user)


def update_case(database: Database, case_id: str, body: dict, user: dict) -> dict:
    current = database.cases.find_one({"id": case_id})
    if not current:
        raise CaseError(404, "案例不存在")
    if not _can_write(current, user):
        raise CaseError(403, "无权编辑该案例")
    if current["workflowStatus"] != "draft":
        raise CaseError(409, "案例当前不可编辑")
    document = body.get("document")
    if document is not None:
        from app.modules.cases.citations import citations_resolve

        citations_resolve(database, case_id, document, None)
    updated = _cas_update(database, case_id, body)
    return internal_case_view(updated, user)


def _cas_update(database: Database, case_id: str, body: dict) -> dict:
    changes = {
        key: body[key] for key in ("title", "document") if body.get(key) is not None
    }
    if body.get("tag_ids") is not None:
        _apply_tags(database, changes, body["tag_ids"])
    changes["updatedAt"] = _now()
    updated = database.cases.find_one_and_update(
        {"id": case_id, "revision": body["revision"]},
        {"$set": changes, "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if updated:
        return updated
    current = database.cases.find_one({"id": case_id})
    raise RevisionConflict(current["revision"])


def _apply_tags(database: Database, changes: dict, tag_ids: list) -> None:
    from app.modules.tags.service import ensure_tags_exist

    ensure_tags_exist(database, tag_ids)
    changes["tagIds"] = list(dict.fromkeys(tag_ids))[:50]
