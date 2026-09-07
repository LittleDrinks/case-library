from __future__ import annotations

import secrets
from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.database import Database

from app.modules.attachments.service import attachment_view, snapshot_attachments
from app.modules.case_sources.service import snapshot_case_sources
from app.modules.cases.citations import citations_resolve
from app.modules.cases.service import (
    CaseError,
    RevisionConflict,
    case_metadata,
    internal_case_view,
)
from app.modules.cases.submission_check import submission_issues
from app.modules.cases.snapshots import (
    create_snapshot,
    list_snapshots,
    rollback_snapshot,
)
from app.modules.case_materials.service import snapshot_materials
from app.modules.search.outbox import SearchOutbox


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8)}"


def _require_owner(case: dict, user: dict) -> None:
    if case["ownerId"] != user["id"]:
        raise CaseError(403, "仅案例作者可执行此操作")


def _require_admin(user: dict) -> None:
    if user["role"] != "admin":
        raise CaseError(403, "仅管理员可执行此操作")


def _require_revision(case: dict, revision: int) -> None:
    if case["revision"] != revision:
        raise RevisionConflict(case["revision"])


# 作者已投稿且审核结论未定的状态：仅在这些状态下作者可撤回。
WITHDRAWABLE_STATES = ("pending", "reviewing")
SUBMISSION_FIELDS = ("submittedVersionId", "submittedAt", "reviewStartedAt")


def _authorize(case: dict, user: dict, command: str) -> None:
    if command == "reopen":
        if case["ownerId"] == user["id"]:
            return
        return _require_admin(user)
    if command in {"submit", "withdraw", "snapshot", "rollback"}:
        _require_owner(case, user)
    else:
        _require_admin(user)


def _version(
    case: dict, user: dict, now: str, attachments: list[dict], materials: list[dict],
    case_sources: list[dict],
) -> dict:
    number = case.get("versionNumber", 0) + 1
    return {
        "id": _id("cv"), "caseId": case["id"], "number": number,
        "kind": "submission", "title": case["title"],
        "summary": case.get("summary", ""), "document": case["document"],
        "attachments": attachments, "materials": materials,
        "caseSources": case_sources, "metadata": case_metadata(case),
        "sourceRevision": case["revision"], "createdBy": user["id"], "createdAt": now,
    }


def _event(case: dict, user: dict, version: dict, now: str, action: str) -> dict:
    return {
        "id": _id("ce"),
        "caseId": case["id"],
        "action": action,
        "versionId": version["id"],
        "round": version["number"],
        "actorId": user["id"],
        "actorRole": user["role"],
        "createdAt": now,
    }


def _validate_submission(database: Database, case: dict) -> None:
    issues = submission_issues(database, case)
    if issues:
        raise CaseError(422, "；".join(issues))


def _submit(database: Database, case: dict, user: dict, session) -> dict:
    _require_owner(case, user)
    if case["workflowStatus"] != "draft":
        raise CaseError(409, "仅工作版本可提交")
    citations_resolve(database, case["id"], case["document"], session)
    _validate_submission(database, case)
    now = _now()
    attachments = snapshot_attachments(database, case["id"], session)
    materials = snapshot_materials(database, case["id"], session)
    case_sources = snapshot_case_sources(database, case["id"], session)
    version = _version(case, user, now, attachments, materials, case_sources)
    event = _event(case, user, version, now, "submit")
    updated = _mark_pending(database, case, version, now, session)
    if not updated:
        raise CaseError(409, "案例状态已变化")
    database.case_versions.insert_one(version, session=session)
    database.lifecycle_events.insert_one(event, session=session)
    return _result(updated, version, event, user)


def _mark_pending(database, case: dict, version: dict, now: str, session) -> dict:
    changes = {
        "workflowStatus": "pending",
        "submittedVersionId": version["id"],
        "submittedAt": now,
        "updatedAt": now,
        "versionNumber": version["number"],
    }
    return _write_case(
        database,
        {"id": case["id"], "revision": case["revision"], "workflowStatus": "draft"},
        {"$set": changes, "$unset": {"lastReview": ""}, "$inc": {"revision": 1}},
        session,
    )


def _clean(record: dict) -> dict:
    cleaned = {key: value for key, value in record.items() if key != "_id"}
    if "attachments" in cleaned:
        cleaned["attachments"] = [
            attachment_view(row) for row in cleaned["attachments"]
        ]
    if "materials" not in cleaned:
        cleaned["materials"] = []
    if "caseSources" not in cleaned:
        cleaned["caseSources"] = []
    return cleaned


def _result(case: dict, version: dict, event: dict, user: dict) -> dict:
    if not case:
        raise CaseError(409, "案例状态已变化")
    return {
        "case": internal_case_view(case, user),
        "version": _clean(version),
        "event": _clean(event),
    }


def _submitted_version(database, case: dict, session) -> dict:
    version = database.case_versions.find_one(
        {"id": case.get("submittedVersionId"), "caseId": case["id"]}, session=session
    )
    if not version:
        raise CaseError(409, "待审版本不存在")
    return version


def _published_version(database, case: dict, session) -> dict:
    version = database.case_versions.find_one(
        {"id": case.get("publishedVersionId"), "caseId": case["id"]}, session=session
    )
    if not version:
        raise CaseError(409, "公开版本不存在")
    return version


def _write_case(database, query: dict, update: dict, session):
    return database.cases.find_one_and_update(
        query, update, session=session, return_document=ReturnDocument.AFTER
    )


def _change_status(
    database, case: dict, expected: str, changes: dict, session, consume: bool = False
):
    query = {
        "id": case["id"],
        "revision": case["revision"],
        "workflowStatus": expected,
        "submittedVersionId": case.get("submittedVersionId"),
    }
    update = {"$set": {**changes, "updatedAt": _now()}, "$inc": {"revision": 1}}
    if consume:
        update["$unset"] = {field: "" for field in SUBMISSION_FIELDS}
    return _write_case(database, query, update, session)


def _start(database, case: dict, user: dict, session) -> dict:
    _require_admin(user)
    if case["workflowStatus"] != "pending":
        raise CaseError(409, "仅待审案例可开始审核")
    version, now = _submitted_version(database, case, session), _now()
    event = _event(case, user, version, now, "start")
    database.lifecycle_events.insert_one(event, session=session)
    updated = _change_status(
        database,
        case,
        "pending",
        {"workflowStatus": "reviewing", "reviewStartedAt": now},
        session,
    )
    return _result(updated, version, event, user)


def _withdraw(database, case: dict, user: dict, session) -> dict:
    _require_owner(case, user)
    if case["workflowStatus"] not in WITHDRAWABLE_STATES:
        raise CaseError(409, "审核结论产生前方可撤回")
    version, now = _submitted_version(database, case, session), _now()
    event = _event(case, user, version, now, "withdraw")
    updated = _mark_withdrawn(database, case, version, now, session)
    if not updated:
        raise CaseError(409, "案例状态已变化")
    database.lifecycle_events.insert_one(event, session=session)
    return _result(updated, version, event, user)


def _mark_withdrawn(database, case: dict, version: dict, now: str, session) -> dict:
    query = {
        "id": case["id"],
        "revision": case["revision"],
        "workflowStatus": {"$in": list(WITHDRAWABLE_STATES)},
        "submittedVersionId": version["id"],
    }
    update = {
        "$set": {"workflowStatus": "draft", "updatedAt": now},
        "$unset": {**{field: "" for field in SUBMISSION_FIELDS}, "lastReview": ""},
        "$inc": {"revision": 1},
    }
    return _write_case(database, query, update, session)


def _approve(database, case: dict, body: dict, user: dict, session) -> dict:
    _require_review_conclusion(case, body)
    version, now = _submitted_version(database, case, session), _now()
    event = _event(case, user, version, now, "approve")
    database.lifecycle_events.insert_one(event, session=session)
    updated = _publish_approved_version(
        database,
        case,
        version,
        now,
        session,
    )
    return _result(updated, version, event, user)


def _require_active_review(case: dict) -> None:
    if case["workflowStatus"] != "reviewing":
        raise CaseError(409, "仅审核中的案例可产生审核结论")


def _require_review_conclusion(case: dict, body: dict) -> None:
    _require_active_review(case)
    if body.get("submittedVersionId") != case.get("submittedVersionId"):
        raise CaseError(409, "待审版本已变化")


def _publication_changes(version: dict, now: str) -> dict:
    return {
        "workflowStatus": "published",
        "publicationStatus": "public",
        "publishedVersionId": version["id"],
        "publishedAt": now,
    }


def _publish_approved_version(database, case, version, now, session):
    replaced = _replaced_version(database, case, session)
    updated = _change_status(
        database,
        case,
        "reviewing",
        _publication_changes(version, now),
        session,
        consume=True,
    )
    if not updated:
        raise CaseError(409, "案例状态已变化")
    _move_material_references(database, replaced, version, session)
    _record_publication(database, case["id"], version, False, session, replaced)
    return updated


def _adjust_material_references(database, version: dict, amount: int, session) -> None:
    material_ids = _material_ids(version)
    if not material_ids:
        return
    database.materials.update_many(
        {"id": {"$in": material_ids}},
        {"$inc": {"publicReferenceCount": amount}},
        session=session,
    )


def _material_ids(version: dict) -> list[str]:
    return list(dict.fromkeys(row["id"] for row in version.get("materials", [])))


def _replaced_version(database, case: dict, session) -> dict | None:
    previous = case.get("publishedVersionId")
    if case.get("publicationStatus") != "public" or not previous:
        return None
    if previous == case.get("submittedVersionId"):
        return None
    return database.case_versions.find_one(
        {"id": previous, "caseId": case["id"]}, session=session
    )


def _move_material_references(database, removed, added: dict, session) -> None:
    if removed:
        _adjust_material_references(database, removed, -1, session)
    _adjust_material_references(database, added, 1, session)


def _record_publication(
    database, case_id, version, revoke, session, replaced: dict | None = None
) -> None:
    current = _material_ids(version)
    keys = [f"case:{case_id}"] + [f"material:{mid}" for mid in current]
    if replaced:
        keys += [f"material:{mid}" for mid in _material_ids(replaced)]
    revoked = keys if revoke else _removed_material_keys(current, replaced)
    SearchOutbox(database).record(
        list(dict.fromkeys(keys)), revoke=revoked, session=session
    )


def _removed_material_keys(current: list[str], replaced: dict | None) -> list[str]:
    if not replaced:
        return []
    return [
        f"material:{mid}"
        for mid in _material_ids(replaced)
        if mid not in current
    ]


def _require_review_return(case: dict, body: dict) -> None:
    _require_active_review(case)
    if body.get("submittedVersionId") != case.get("submittedVersionId"):
        raise CaseError(409, "待审版本已变化")


def _review_annotation_ids(database, case: dict, version: dict, session) -> list[str]:
    rows = database.annotations.find(
        {
            "caseId": case["id"],
            "versionId": version["id"],
            "source": {"$in": ["admin", "ai"]},
        },
        session=session,
    ).sort("createdAt", 1)
    return [row["id"] for row in rows]


def _review_event(case, user: dict, version: dict, body: dict, ids: list[str]) -> dict:
    event = _event(case, user, version, _now(), body["command"])
    event.update(
        {
            "reasonType": body["reasonType"],
            "summary": body.get("summary") or "",
            "annotationIds": ids,
        }
    )
    return event


def _last_review(event: dict, version: dict) -> dict:
    return {
        "action": event["action"],
        "reasonType": event["reasonType"],
        "summary": event["summary"],
        "annotationIds": event["annotationIds"],
        "versionNumber": version["number"],
        "actorId": event["actorId"],
        "createdAt": event["createdAt"],
    }


def _mark_returned(database, case: dict, version: dict, event: dict, session) -> dict:
    query = {
        "id": case["id"],
        "revision": case["revision"],
        "workflowStatus": "reviewing",
        "submittedVersionId": version["id"],
    }
    update = {
        "$set": {
            "workflowStatus": "draft",
            "lastReview": _last_review(event, version),
            "updatedAt": event["createdAt"],
        },
        "$unset": {field: "" for field in SUBMISSION_FIELDS},
        "$inc": {"revision": 1},
    }
    return _write_case(database, query, update, session)


def _return_for_revision(database, case: dict, body: dict, user: dict, session) -> dict:
    _require_review_return(case, body)
    version = _submitted_version(database, case, session)
    ids = _review_annotation_ids(database, case, version, session)
    event = _review_event(case, user, version, body, ids)
    updated = _mark_returned(database, case, version, event, session)
    if not updated:
        raise CaseError(409, "案例状态已变化")
    database.lifecycle_events.insert_one(event, session=session)
    return _result(updated, version, event, user)


def _publication_change(database, case: dict, user: dict, action: str, session) -> dict:
    expected, target = _publication_states(action)
    if case["publicationStatus"] != expected:
        raise CaseError(409, "案例当前不能执行该发布操作")
    version, now = _published_version(database, case, session), _now()
    updated = _set_publication(database, case, version, expected, target, now, session)
    if not updated:
        raise CaseError(409, "案例状态已变化")
    _adjust_material_references(
        database, version, -1 if action == "hide" else 1, session
    )
    _record_publication(database, case["id"], version, action == "hide", session)
    event = _event(case, user, version, now, action)
    database.lifecycle_events.insert_one(event, session=session)
    return _result(updated, version, event, user)


def _publication_states(action: str) -> tuple[str, str]:
    return ("public", "hidden") if action == "hide" else ("hidden", "public")


def _published_query(case: dict, version: dict, status: str) -> dict:
    return {
        "id": case["id"],
        "revision": case["revision"],
        "publicationStatus": status,
        "publishedVersionId": version["id"],
    }


def _set_publication(database, case, version, expected, target, now, session) -> dict:
    return database.cases.find_one_and_update(
        _published_query(case, version, expected),
        {
            "$set": {"publicationStatus": target, "updatedAt": now},
            "$inc": {"revision": 1},
        },
        session=session,
        return_document=ReturnDocument.AFTER,
    )


def _reopen(database, case: dict, user: dict, session) -> dict:
    if case["workflowStatus"] != "published":
        raise CaseError(409, "仅已发布案例可另起新稿")
    if case["ownerId"] != user["id"] and case["publicationStatus"] != "hidden":
        raise CaseError(409, "仅已隐藏案例可下线编辑")
    version, now = _published_version(database, case, session), _now()
    updated = _mark_reopened(database, case, version, now, session)
    if not updated:
        raise CaseError(409, "案例状态已变化")
    event = _event(case, user, version, now, "reopen")
    database.lifecycle_events.insert_one(event, session=session)
    return _result(updated, version, event, user)


def _mark_reopened(database, case: dict, version: dict, now: str, session) -> dict:
    update = {
        "$set": {"workflowStatus": "draft", "updatedAt": now},
        "$unset": {field: "" for field in SUBMISSION_FIELDS},
        "$inc": {"revision": 1},
    }
    query = _published_query(case, version, case["publicationStatus"])
    return _write_case(database, query, update, session)


def _admin_action(database, case: dict, body: dict, user: dict, session) -> dict:
    if body["command"] in {"reject", "supplement"}:
        return _return_for_revision(database, case, body, user, session)
    if body["command"] in {"hide", "restore"}:
        return _publication_change(database, case, user, body["command"], session)
    return _approve(database, case, body, user, session)


def _execute(database, case_id: str, body: dict, user: dict, session) -> dict:
    case = database.cases.find_one({"id": case_id}, session=session)
    if not case:
        raise CaseError(404, "案例不存在")
    _authorize(case, user, body["command"])
    _require_revision(case, body["revision"])
    if body["command"] == "submit":
        return _submit(database, case, user, session)
    if body["command"] == "withdraw":
        return _withdraw(database, case, user, session)
    if body["command"] == "start":
        return _start(database, case, user, session)
    if body["command"] == "snapshot":
        return create_snapshot(database, case, user, session)
    if body["command"] == "rollback":
        return rollback_snapshot(database, case, user, body.get("targetId"), session)
    if body["command"] == "reopen":
        return _reopen(database, case, user, session)
    return _admin_action(database, case, body, user, session)


def execute_lifecycle(database: Database, case_id: str, body: dict, user: dict) -> dict:
    with database.client.start_session() as session:
        return session.with_transaction(
            lambda active: _execute(database, case_id, body, user, active)
        )


def get_history(database: Database, case_id: str, user: dict) -> dict:
    case = database.cases.find_one({"id": case_id})
    if not case:
        raise CaseError(404, "案例不存在")
    if user["role"] != "admin" and case["ownerId"] != user["id"]:
        raise CaseError(403, "无权查看版本历史")
    versions = database.case_versions.find({"caseId": case_id}).sort("number", 1)
    events = database.lifecycle_events.find({"caseId": case_id}).sort("createdAt", 1)
    return {
        "caseId": case_id,
        "versions": [_clean(row) for row in versions],
        "snapshots": list_snapshots(database, case_id),
        "events": [_clean(row) for row in events],
    }
