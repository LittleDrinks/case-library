from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from app.core.config import Settings
from app.core.database import connect
from app.modules.search.client import create_client, wait_task
from app.modules.search.projection import case_catalog_ids


DATABASE_NAME = "case_library_worker361"
INDEX_PREFIX = "catalog_worker361"
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
USER_ID_PATTERN = re.compile(r"^u-[a-f0-9]{24}$")
CASE_ID_PATTERN = re.compile(r"^c-[a-f0-9]{12}$")
TEST_USERNAME_PATTERN = re.compile(
    r"^realai361-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"
)
SAFE_FAILURE_CODES = {
    "invalid_report",
    "invalid_synthetic_user_id",
    "invalid_synthetic_case_id",
    "invalid_synthetic_id",
    "database_scope_mismatch",
    "index_scope_mismatch",
    "synthetic_user_scope_mismatch",
    "synthetic_case_owner_mismatch",
    "case_owner_required",
    "synthetic_case_missing",
    "test_username_required",
    "test_username_mismatch",
    "synthetic_case_ambiguous",
    "synthetic_user_missing",
    "ownership_root_changed",
}


def _read_report(path: str) -> tuple[dict, str | None]:
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = report.get("syntheticIds")
    if not isinstance(ids, dict):
        raise ValueError("invalid_report")
    cleanup_identity = report.get("cleanupIdentity")
    username = cleanup_identity.get("username") if isinstance(cleanup_identity, dict) else None
    if ids.get("userId") is not None and not USER_ID_PATTERN.fullmatch(
        str(ids["userId"])
    ):
        raise ValueError("invalid_synthetic_user_id")
    if ids.get("caseId") is not None and not CASE_ID_PATTERN.fullmatch(
        str(ids["caseId"])
    ):
        raise ValueError("invalid_synthetic_case_id")
    for name in ("userId", "caseId", "threadId", "runId"):
        value = ids.get(name)
        if value is not None and (
            not isinstance(value, str) or not ID_PATTERN.fullmatch(value)
        ):
            raise ValueError("invalid_synthetic_id")
    if ids.get("caseId") is not None and ids.get("userId") is None:
        raise ValueError("case_owner_required")
    if username is not None and (
        not isinstance(username, str) or not TEST_USERNAME_PATTERN.fullmatch(username)
    ):
        raise ValueError("test_username_required")
    if ids.get("userId") is not None and username is None:
        raise ValueError("test_username_required")
    return ids, username


def _remove_search_documents(database, settings: Settings, case_id: str) -> None:
    client = create_client(settings.search_url, settings.search_api_key_file)
    state = database.search_catalog_generation.find_one({"_id": "catalog"}) or {}
    index_uids = {
        settings.search_index_uid,
        state.get("indexUid"),
        *state.get("retiredIndexUids", []),
    }
    for index_uid in sorted(value for value in index_uids if isinstance(value, str)):
        if index_uid != INDEX_PREFIX and not index_uid.startswith(
            f"{INDEX_PREFIX}-generation-"
        ):
            continue
        wait_task(
            client,
            client.index(index_uid).delete_documents(case_catalog_ids(case_id)),
        )


def _remove_case_records(database, case_id: str) -> None:
    thread_ids = database.agent_threads.distinct("id", {"caseId": case_id})
    run_ids = database.agent_runs.distinct(
        "id", {"threadId": {"$in": thread_ids}}
    ) if thread_ids else []

    if thread_ids:
        thread_scope = {"threadId": {"$in": thread_ids}}
        database.agent_messages.delete_many(thread_scope)
        database.agent_thread_events.delete_many(thread_scope)
        database.agent_writes.delete_many({
            "$or": [thread_scope, {"runId": {"$in": run_ids}}],
        })
    database.agent_artifacts.delete_many({
        "$or": [
            {"caseId": case_id},
            {"threadId": {"$in": thread_ids}},
            {"runId": {"$in": run_ids}},
        ],
    })
    if thread_ids:
        database.agent_runs.delete_many({"threadId": {"$in": thread_ids}})
    database.agent_threads.delete_many({"id": {"$in": thread_ids}})

    for collection in (
        "annotations",
        "attachments",
        "case_materials",
        "case_sources",
        "case_snapshots",
        "case_versions",
        "lifecycle_events",
    ):
        database[collection].delete_many({"caseId": case_id})
    logical_key = f"case:{case_id}"
    database.search_outbox.delete_many({"logicalKey": logical_key})
    database.search_revocations.delete_one({"_id": logical_key})


def _remove_user_records(database, user_id: str) -> None:
    database.sessions.delete_many({"user_id": user_id})
    database.ai_user_settings.delete_one({"_id": user_id})

    escaped = re.escape(user_id)
    for pattern in (
        rf"^rate:chat:{escaped}:",
        rf"^rate:discover:{escaped}:",
        rf"^concurrent:chat:user:{escaped}:",
    ):
        database.ai_usage.delete_many({"_id": {"$regex": pattern}})


def _remove_ownership_roots(
    database, case_id: str | None, user_id: str, username: str
) -> None:
    with database.client.start_session() as session:
        with session.start_transaction():
            if case_id:
                case_result = database.cases.delete_one(
                    {"id": case_id, "ownerId": user_id}, session=session
                )
                if case_result.deleted_count != 1:
                    raise ValueError("ownership_root_changed")
            user_result = database.users.delete_one(
                {
                    "id": user_id,
                    "username": username,
                    "role": "user",
                    "campus_verified": False,
                },
                session=session,
            )
            if user_result.deleted_count != 1:
                raise ValueError("ownership_root_changed")


def clear(report_path: str) -> None:
    ids, username = _read_report(report_path)
    user_id = ids.get("userId")
    case_id = ids.get("caseId")
    if not user_id and not case_id and not username:
        return

    settings = Settings.from_environment()
    if settings.mongo_database != DATABASE_NAME:
        raise ValueError("database_scope_mismatch")
    if settings.search_index_uid != INDEX_PREFIX:
        raise ValueError("index_scope_mismatch")

    mongo, database = connect(settings)
    try:
        user = None
        if username:
            user = database.users.find_one(
                {"username": username},
                {"id": 1, "username": 1, "role": 1, "campus_verified": 1},
            )
        if user_id:
            user_by_id = database.users.find_one(
                {"id": user_id},
                {"username": 1, "role": 1, "campus_verified": 1},
            )
            if not user_by_id:
                raise ValueError("synthetic_user_missing")
            if user_by_id and user_by_id.get("username") != username:
                raise ValueError("test_username_mismatch")
            if user and user.get("id") != user_id:
                raise ValueError("test_username_mismatch")
            user = user_by_id or user
        elif user:
            user_id = user.get("id")
            if not isinstance(user_id, str) or not USER_ID_PATTERN.fullmatch(user_id):
                raise ValueError("invalid_synthetic_user_id")
        if user and (
            user.get("role") != "user" or user.get("campus_verified") is not False
        ):
            raise ValueError("synthetic_user_scope_mismatch")
        if not case_id and user_id:
            matches = list(
                database.cases.find({"ownerId": user_id}, {"id": 1}).limit(2)
            )
            if len(matches) > 1:
                raise ValueError("synthetic_case_ambiguous")
            if matches:
                case_id = matches[0].get("id")
                if not isinstance(case_id, str) or not CASE_ID_PATTERN.fullmatch(
                    case_id
                ):
                    raise ValueError("invalid_synthetic_case_id")
        if case_id:
            case = database.cases.find_one({"id": case_id}, {"ownerId": 1})
            if not case:
                raise ValueError("synthetic_case_missing")
            if case.get("ownerId") != user_id:
                raise ValueError("synthetic_case_owner_mismatch")
            _remove_search_documents(database, settings, case_id)
            _remove_case_records(database, case_id)
        if user_id:
            _remove_user_records(database, user_id)
            _remove_ownership_roots(database, case_id, user_id, username)
    finally:
        mongo.close()


def main() -> int:
    if len(sys.argv) != 2:
        print('{"cleanup":"failed","failureCode":"invalid_invocation"}')
        return 2
    try:
        clear(sys.argv[1])
    except Exception as error:
        if isinstance(error, json.JSONDecodeError):
            failure_code = "invalid_report"
        elif isinstance(error, OSError):
            failure_code = "report_unavailable"
        elif (
            isinstance(error, ValueError)
            and len(error.args) == 1
            and isinstance(error.args[0], str)
            and error.args[0] in SAFE_FAILURE_CODES
        ):
            failure_code = error.args[0]
        else:
            failure_code = "cleanup_dependency_failure"
        print(json.dumps({"cleanup": "failed", "failureCode": failure_code}))
        return 1
    print('{"cleanup":"passed"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
