from __future__ import annotations

import secrets
from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.database import Database

from app.modules.cases.service import CaseError


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _view(annotation: dict) -> dict:
    return {key: value for key, value in annotation.items() if key != "_id"}


def _case(database: Database, case_id: str, user: dict) -> dict:
    case = database.cases.find_one({"id": case_id})
    if not case:
        raise CaseError(404, "案例不存在")
    if user["role"] != "admin" and case["ownerId"] != user["id"]:
        raise CaseError(403, "无权查看案例批注")
    return case


def _review_version(database: Database, case: dict) -> dict:
    version = database.case_versions.find_one(
        {
            "id": case.get("submittedVersionId"),
            "caseId": case["id"],
        }
    )
    if case["workflowStatus"] != "reviewing" or not version:
        raise CaseError(409, "仅审核中的版本可添加批注")
    return version


def _node_text(node: dict) -> str:
    own = node.get("text", "")
    return own + "".join(_node_text(child) for child in node.get("content", []))


def _sections(document: dict) -> dict[str, str]:
    sections, current = {}, ""
    for node in document.get("content", []):
        level = node.get("attrs", {}).get("level")
        if node.get("type") == "heading" and level in {1, 2}:
            current = _node_text(node).strip()
            sections[current] = current
        elif current:
            sections[current] += _node_text(node)
    return sections


def _require_anchor(version: dict, body: dict) -> None:
    section_text = _sections(version["document"]).get(body["section"], "")
    if body["quote"].strip() not in section_text:
        raise CaseError(409, "批注选区不属于待审版本小节")


def create_annotation(database: Database, case_id: str, body: dict, user: dict) -> dict:
    case = _case(database, case_id, user)
    if user["role"] != "admin" or body["source"] != "admin":
        raise CaseError(403, "仅管理员可添加人工审核批注")
    version = _review_version(database, case)
    _require_anchor(version, body)
    annotation = {
        "id": f"an-{secrets.token_hex(8)}",
        "caseId": case_id,
        "versionId": version["id"],
        **body,
        "status": "pending",
        "replies": [],
        "createdBy": user["id"],
        "createdAt": _now(),
    }
    database.annotations.insert_one(annotation)
    return _view(annotation)


def list_annotations(database: Database, case_id: str, user: dict) -> list[dict]:
    _case(database, case_id, user)
    rows = database.annotations.find({"caseId": case_id}).sort("createdAt", 1)
    return [_view(row) for row in rows]


def _annotation(database: Database, case_id: str, annotation_id: str) -> dict:
    annotation = database.annotations.find_one({"id": annotation_id, "caseId": case_id})
    if not annotation:
        raise CaseError(404, "批注不存在")
    return annotation


def add_reply(
    database: Database, case_id: str, annotation_id: str, content: str, user: dict
) -> dict:
    _case(database, case_id, user)
    _annotation(database, case_id, annotation_id)
    reply = {
        "id": f"ar-{secrets.token_hex(8)}",
        "content": content,
        "createdBy": user["id"],
        "createdAt": _now(),
    }
    updated = database.annotations.find_one_and_update(
        {"id": annotation_id, "caseId": case_id},
        {"$push": {"replies": reply}},
        return_document=ReturnDocument.AFTER,
    )
    return _view(updated)


def _require_status_actor(case: dict, user: dict, status: str) -> None:
    if status == "resolved" and case["ownerId"] != user["id"]:
        raise CaseError(403, "仅案例作者可解决批注")
    if status == "pending" and user["role"] != "admin":
        raise CaseError(403, "仅管理员可重开批注")


def change_status(
    database: Database, case_id: str, annotation_id: str, status: str, user: dict
) -> dict:
    case = _case(database, case_id, user)
    _annotation(database, case_id, annotation_id)
    _require_status_actor(case, user, status)
    expected = "pending" if status == "resolved" else "resolved"
    updated = database.annotations.find_one_and_update(
        {"id": annotation_id, "caseId": case_id, "status": expected},
        {"$set": {"status": status}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise CaseError(409, "批注状态已变化")
    return _view(updated)
