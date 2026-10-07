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
    return (
        case["publicationStatus"] == "public"
        or _is_internal(case, user)
        or bool(
            user
            and user["role"] == "admin"
            and case.get("workflowStatus") == "published"
            and case.get("publishedVersionId")
        )
    )


def _is_internal(case: dict, user: dict | None) -> bool:
    return bool(user and case["ownerId"] == user["id"])


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
    if user and user["role"] == "admin":
        return _admin_published_view(database, case, user)
    from app.modules.cases.published import PublishedCaseReader

    return PublishedCaseReader(database).get(case)


def _admin_published_view(database, case: dict, user: dict) -> dict:
    version = database.case_versions.find_one(
        {"id": case.get("publishedVersionId"), "caseId": case["id"]}
    )
    if not version:
        raise CaseError(404, "案例不存在")
    return frozen_case_view(case, version, user)


def frozen_case_view(case: dict, version: dict, user: dict) -> dict:
    from app.modules.cases.published import published_view

    view = published_view(case, version)
    view.update(
        {
            "workflowStatus": case["workflowStatus"],
            "publicationStatus": case["publicationStatus"],
            "revision": case["revision"],
            "publishedVersionId": case.get("publishedVersionId"),
            "submittedVersionId": case.get("submittedVersionId"),
            "submittedAt": case.get("submittedAt"),
            "ownerId": case["ownerId"],
            "availableActions": available_actions(case, user),
        }
    )
    return view


def get_review_case(
    database: Database, case_id: str, user: dict, version_id: str | None = None
) -> dict:
    from app.modules.cases.published import admin_review_record

    if user.get("role") != "admin":
        raise CaseError(403, "仅管理员可查看投稿审核")
    case = database.cases.find_one({"id": case_id})
    if not case:
        raise CaseError(404, "投稿不存在")
    selected = version_id or case.get("submittedVersionId") or case.get("publishedVersionId")
    version, status = admin_review_record(database, case, user, selected)
    if not version:
        raise CaseError(404, "投稿不存在")
    view = frozen_case_view(case, version, user)
    view["reviewVersionId"] = version["id"]
    view["reviewRecordStatus"] = status
    is_current_review_version = bool(
        (status in {"pending", "reviewing"}
            and case.get("submittedVersionId") == version["id"])
        or (
            status == "published"
            and case.get("workflowStatus") == "published"
            and case.get("publishedVersionId") == version["id"]
        )
    )
    view["isCurrentReviewVersion"] = is_current_review_version
    if not is_current_review_version:
        view["availableActions"] = []
        view["revision"] = version["sourceRevision"]
    if status == "returned":
        event = database.lifecycle_events.find_one(
            {"caseId": case_id, "versionId": version["id"], "action": "reject"}
        )
        if event:
            view["reviewFeedback"] = {
                "action": "reject",
                "reasonTypes": event.get("reasonTypes", []),
                "message": event.get("message", ""),
                "annotationIds": event.get("annotationIds", []),
                "versionNumber": version["number"],
                "actorId": event["actorId"],
                "createdAt": event["createdAt"],
            }
    return view


def list_cases(database: Database, user: dict | None, scope: str) -> list[dict]:
    if scope == "public":
        return _list_public_cases(database)
    if scope == "admin":
        return _list_admin_cases(database, user)
    return _list_my_cases(database, user)


DRAFT_PAGE_FIELDS = ("id", "title", "updatedAt")


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
        .sort([("updatedAt", DESCENDING), ("id", DESCENDING)])
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
    from app.modules.cases.published import admin_review_record

    if not user or user["role"] != "admin":
        raise CaseError(403, "仅管理员可查看管理队列")
    rows = database.cases.find(
        {
            "$or": [
                {"workflowStatus": {"$in": ["pending", "reviewing"]}},
                {
                    "workflowStatus": "published",
                    "publicationStatus": {"$in": ["public", "hidden"]},
                },
            ]
        }
    ).sort("updatedAt", DESCENDING)
    current = [
        card
        for case in rows
        if (card := _admin_case_card(database, case, user)) is not None
    ]
    seen = {
        (card["id"], card["reviewVersionId"])
        for card in current
        if card.get("reviewVersionId")
    }
    events = database.lifecycle_events.find(
        {"action": {"$in": ["reject", "withdraw"]}},
        {"caseId": 1, "versionId": 1, "action": 1},
    ).sort("createdAt", DESCENDING)
    for event in events:
        key = (event.get("caseId"), event.get("versionId"))
        if key in seen:
            continue
        case = database.cases.find_one({"id": key[0]})
        if not case:
            continue
        version, status = admin_review_record(database, case, user, key[1])
        if not version:
            continue
        snapshot = frozen_case_view(case, version, user)
        card = case_card(snapshot, include_owner=True, user=user)
        card.update({
            "reviewVersionId": version["id"],
            "reviewRecordStatus": status,
            "versionNumber": version["number"],
        })
        current.append(card)
        seen.add(key)
    return current


def _admin_case_card(database, case: dict, user: dict) -> dict | None:
    version_id = (
        case.get("submittedVersionId")
        if case.get("workflowStatus") in {"pending", "reviewing"}
        else case.get("publishedVersionId")
    )
    version = database.case_versions.find_one(
        {"id": version_id, "caseId": case["id"]}
    )
    if not version:
        return None
    snapshot = frozen_case_view(case, version, user)
    card = case_card(snapshot, include_owner=True, user=user)
    card.update({"reviewVersionId": version["id"], "versionNumber": version["number"]})
    card["reviewRecordStatus"] = (
        case.get("workflowStatus")
        if case.get("workflowStatus") in {"pending", "reviewing"}
        else "published"
    )
    return card


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
    return run_transaction(
        database, lambda session: _update_case(database, case_id, body, user, session)
    )


def _update_case(database: Database, case_id: str, body: dict, user: dict, session) -> dict:
    current = _editable_case(database, case_id, user, session)
    document = body.get("document")
    mapping = _update_mapping(database, case_id, current, document, body, session)
    updated = _cas_update(database, case_id, body, session)
    _reconcile_update(database, case_id, current, document, updated, body, session, mapping)
    return internal_case_view(updated, user)


def _editable_case(database, case_id: str, user: dict, session) -> dict:
    current = database.cases.find_one({"id": case_id}, session=session)
    if not current:
        raise CaseError(404, "案例不存在")
    if not _can_write(current, user):
        raise CaseError(403, "无权编辑该案例")
    if current["workflowStatus"] != "draft":
        raise CaseError(409, "案例当前不可编辑")
    return current


def _update_mapping(database, case_id, current, document, body, session):
    if document is None:
        return None
    from app.modules.cases.citations import citations_resolve
    from app.modules.annotations.service import document_mapping

    citations_resolve(database, case_id, document, session)
    return document_mapping(current["document"], document, body.get("steps"))


def _reconcile_update(database, case_id, current, document, updated, body, session, mapping):
    if document is None:
        return
    from app.modules.annotations.service import reconcile_document_annotations

    reconcile_document_annotations(
        database, case_id, current["document"], document, updated["revision"],
        body.get("steps"), session, mapping,
    )


def _cas_update(database: Database, case_id: str, body: dict, session) -> dict:
    changes = {
        key: body[key] for key in ("title", "document") if body.get(key) is not None
    }
    if body.get("tag_ids") is not None:
        _apply_tags(database, changes, body["tag_ids"])
    changes["updatedAt"] = _now()
    updated = database.cases.find_one_and_update(
        {"id": case_id, "revision": body["revision"]},
        {"$set": changes, "$inc": {"revision": 1}},
        session=session,
        return_document=ReturnDocument.AFTER,
    )
    if updated:
        return updated
    current = database.cases.find_one({"id": case_id}, session=session)
    raise RevisionConflict(current["revision"])


def _apply_tags(database: Database, changes: dict, tag_ids: list) -> None:
    from app.modules.tags.service import ensure_tags_exist

    ensure_tags_exist(database, tag_ids)
    changes["tagIds"] = list(dict.fromkeys(tag_ids))[:50]
