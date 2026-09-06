"""真实副本集上的撤回/通过并发证据：一笔事务只允许一个审核结论。

需要 LIFECYCLE_MONGODB_URI 指向副本集；数据库由本测试创建并清理。
"""
from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from pymongo import MongoClient

from app.core.database import initialize
from app.modules.cases.lifecycle import execute_lifecycle
from app.modules.cases.service import CaseError

MONGODB_URI = os.environ.get("LIFECYCLE_MONGODB_URI")
pytestmark = pytest.mark.e2e("LIFECYCLE_MONGODB_URI")

OWNER = {"id": "u-race-owner", "name": "作者", "role": "user"}
ADMIN = {"id": "u-race-admin", "name": "审核", "role": "admin"}
RACE_ROUNDS = 5


def _case_record(case_id: str, document: dict) -> dict:
    return {
        "id": case_id,
        "title": "并发证据",
        "summary": "",
        "document": document,
        "revision": 1,
        "workflowStatus": "draft",
        "publicationStatus": "none",
        "versionNumber": 0,
        "ownerId": OWNER["id"],
        "createdAt": "2026-01-01T00:00:00+00:00",
        "updatedAt": "2026-01-01T00:00:00+00:00",
    }


def _document(text: str) -> dict:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def _seed_reviewing(database) -> tuple[str, dict, int]:
    case_id = f"c-race-{uuid.uuid4().hex[:8]}"
    database.cases.insert_one(_case_record(case_id, _document("并发证据正文")))
    submitted = execute_lifecycle(
        database, case_id, {"command": "submit", "revision": 1}, OWNER
    )
    started = execute_lifecycle(
        database,
        case_id,
        {"command": "start", "revision": submitted["case"]["revision"]},
        ADMIN,
    )
    return case_id, submitted, started["case"]["revision"]


def _attempt(database, case_id: str, command: dict, user: dict) -> bool:
    try:
        execute_lifecycle(database, case_id, command, user)
        return True
    except CaseError as error:
        assert error.status_code == 409
        return False


def _race(database, case_id: str, revision: int, version_id: str) -> list[bool]:
    jobs = {
        "withdraw": ({"command": "withdraw", "revision": revision}, OWNER),
        "approve": (
            {
                "command": "approve",
                "revision": revision,
                "submittedVersionId": version_id,
            },
            ADMIN,
        ),
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_attempt, database, case_id, *jobs[name]) for name in jobs]
        return sorted((future.result() for future in futures), reverse=True)


def test_withdraw_and_approve_admit_exactly_one_decision() -> None:
    client = MongoClient(MONGODB_URI)
    name = f"lifecycle_rs_{uuid.uuid4().hex[:8]}"
    database = client[name]
    initialize(database)
    try:
        for _ in range(RACE_ROUNDS):
            case_id, submitted, revision = _seed_reviewing(database)
            assert _race(database, case_id, revision, submitted["version"]["id"]) == [
                True,
                False,
            ]
            case = database.cases.find_one({"id": case_id})
            self_published = case.get("publishedVersionId") == submitted["version"]["id"]
            assert case["workflowStatus"] == ("published" if self_published else "draft")
            assert (case["publicationStatus"] == "public") == self_published
    finally:
        client.drop_database(name)
