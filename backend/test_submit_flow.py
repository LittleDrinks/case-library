#!/usr/bin/env python3
"""Executable submit-flow safety checks."""

import os
import sys
from uuid import uuid4

os.environ["MONGODB_DB_NAME"] = f"case_library_submit_flow_test_{uuid4().hex}"

sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient

import main
from database import create_case, create_user, get_db, get_mongo_client


client = TestClient(main.app)


def auth(username: str):
    return {"Authorization": f"Bearer {main.create_auth_token(username)}"}


def make_case(owner: str, status: str = "draft") -> int:
    return create_case(
        {
            "title": f"{owner}-{status}",
            "type": "TYPE_A",
            "theme": "test",
            "content": "submit flow test",
            "author": owner,
            "owner_username": owner,
            "department": "test",
            "status": status,
            "created_at": "2020-01-01 08:00:00",
            "updated_at": "2020-01-01 08:00:00",
        }
    )


def assert_status(response, expected: int):
    assert response.status_code == expected, (response.status_code, response.text)


def main_test() -> None:
    create_user("ownerflow", "password123", role="normal", must_change_password=False)
    create_user("otherflow", "password123", role="normal", must_change_password=False)
    create_user("adminflow", "password123", role="admin", must_change_password=False)

    other_case = make_case("ownerflow", "draft")
    response = client.post(f"/api/cases/{other_case}/submit", headers=auth("otherflow"))
    assert_status(response, 403)

    owner_case = make_case("ownerflow", "draft")
    response = client.post(f"/api/cases/{owner_case}/submit", headers=auth("ownerflow"))
    assert_status(response, 200)
    stored = get_db().cases.find_one({"id": owner_case})
    assert stored["status"] == "pending_review"
    assert stored.get("submitted_at"), stored

    detail = client.get(f"/api/cases/{owner_case}?increment_view=false", headers=auth("ownerflow"))
    assert_status(detail, 200)
    returned = detail.json()["data"]
    assert returned["submitted_at"] == stored["submitted_at"]
    assert returned["display_at"] == returned["submitted_at"]
    assert returned["created_at"] == "2020-01-01 08:00:00"

    admin_case = make_case("ownerflow", "needs_revision")
    response = client.post(f"/api/cases/{admin_case}/submit", headers=auth("adminflow"))
    assert_status(response, 200)

    illegal_status_cases = {
        "approved": make_case("ownerflow", "approved"),
        "pending_review": make_case("ownerflow", "draft"),
        "deleted": make_case("ownerflow", "draft"),
    }
    get_db().cases.update_one({"id": illegal_status_cases["pending_review"]}, {"$set": {"status": "pending_review"}})
    get_db().cases.update_one({"id": illegal_status_cases["deleted"]}, {"$set": {"status": "deleted"}})

    for status, case_id in illegal_status_cases.items():
        response = client.post(f"/api/cases/{case_id}/submit", headers=auth("ownerflow"))
        assert_status(response, 400)
        stored = get_db().cases.find_one({"id": case_id})
        assert not stored.get("submitted_at"), (status, stored)

    listed = client.get("/api/cases?author=ownerflow&status=all", headers=auth("ownerflow"))
    assert_status(listed, 200)
    listed_case = next(item for item in listed.json()["data"] if item["id"] == owner_case)
    assert listed_case["display_at"] == listed_case["submitted_at"]

    print("submit flow checks passed")


if __name__ == "__main__":
    try:
        main_test()
    finally:
        get_mongo_client().drop_database(os.environ["MONGODB_DB_NAME"])
