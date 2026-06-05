#!/usr/bin/env python3
"""Executable submit-flow safety checks."""

import os
import sys
from pathlib import Path
from uuid import uuid4

os.environ["MONGODB_DB_NAME"] = f"case_library_submit_flow_test_{uuid4().hex}"

sys.path.insert(0, str(Path(__file__).resolve().parent))

import main
from database import create_case, create_user, get_db, get_mongo_client
from fastapi.testclient import TestClient

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
    create_user("forceflow", "oldpass123", role="normal", must_change_password=True)

    response = client.post(
        "/api/auth/login",
        data={"username": "forceflow", "password": "oldpass123"},
    )
    assert_status(response, 200)
    assert response.json()["data"]["must_change_password"] is True

    response = client.post(
        "/api/auth/change-password",
        data={
            "username": "forceflow",
            "old_password": "oldpass123",
            "new_password": "short",
        },
    )
    assert_status(response, 400)

    response = client.post(
        "/api/auth/change-password",
        data={
            "username": "forceflow",
            "old_password": "wrongpass123",
            "new_password": "newpass123",
        },
    )
    assert_status(response, 400)

    response = client.post(
        "/api/auth/change-password",
        data={
            "username": "forceflow",
            "old_password": "oldpass123",
            "new_password": "newpass123",
        },
    )
    assert_status(response, 200)

    response = client.post(
        "/api/auth/login",
        data={"username": "forceflow", "password": "oldpass123"},
    )
    assert_status(response, 401)

    response = client.post(
        "/api/auth/login",
        data={"username": "forceflow", "password": "newpass123"},
    )
    assert_status(response, 200)
    assert response.json()["data"]["must_change_password"] is False

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
    get_db().cases.update_one(
        {"id": illegal_status_cases["pending_review"]}, {"$set": {"status": "pending_review"}}
    )
    get_db().cases.update_one(
        {"id": illegal_status_cases["deleted"]}, {"$set": {"status": "deleted"}}
    )

    for status, case_id in illegal_status_cases.items():
        response = client.post(f"/api/cases/{case_id}/submit", headers=auth("ownerflow"))
        assert_status(response, 400)
        stored = get_db().cases.find_one({"id": case_id})
        assert not stored.get("submitted_at"), (status, stored)

    listed = client.get("/api/cases?author=ownerflow&status=all", headers=auth("ownerflow"))
    assert_status(listed, 200)
    listed_case = next(item for item in listed.json()["data"] if item["id"] == owner_case)
    assert listed_case["display_at"] == listed_case["submitted_at"]

    visibility_case = make_case("ownerflow", "approved")

    response = client.post(
        f"/api/cases/{visibility_case}/visibility",
        data={"hidden": "true"},
        headers=auth("ownerflow"),
    )
    assert_status(response, 403)

    response = client.post(
        f"/api/cases/{visibility_case}/visibility",
        data={"hidden": "true"},
        headers=auth("adminflow"),
    )
    assert_status(response, 200)
    assert response.json()["is_hidden"] is True

    public_list = client.get("/api/cases?status=approved")
    assert_status(public_list, 200)
    assert all(item["id"] != visibility_case for item in public_list.json()["data"])

    admin_list = client.get("/api/cases?status=approved_all", headers=auth("adminflow"))
    assert_status(admin_list, 200)
    admin_listed = next(item for item in admin_list.json()["data"] if item["id"] == visibility_case)
    assert admin_listed["is_hidden"] is True

    response = client.post(
        f"/api/cases/{visibility_case}/visibility",
        data={"hidden": "false"},
        headers=auth("adminflow"),
    )
    assert_status(response, 200)
    assert response.json()["is_hidden"] is False

    public_list = client.get("/api/cases?status=approved")
    assert_status(public_list, 200)
    public_listed = next(item for item in public_list.json()["data"] if item["id"] == visibility_case)
    assert public_listed["is_hidden"] is False

    delete_case_id = make_case("ownerflow", "draft")

    response = client.delete(f"/api/cases/{delete_case_id}")
    assert_status(response, 401)

    response = client.delete(f"/api/cases/{delete_case_id}", headers=auth("otherflow"))
    assert_status(response, 403)

    response = client.delete(f"/api/cases/{delete_case_id}", headers=auth("ownerflow"))
    assert_status(response, 200)

    response = client.get(f"/api/cases/{delete_case_id}", headers=auth("ownerflow"))
    assert_status(response, 404)

    admin_delete_case = make_case("ownerflow", "approved")
    response = client.delete(f"/api/cases/{admin_delete_case}", headers=auth("adminflow"))
    assert_status(response, 200)
    assert response.json()["deleted_stats"]["type"] == "TYPE_A"

    response = client.get(f"/api/cases/{admin_delete_case}", headers=auth("adminflow"))
    assert_status(response, 404)

    review_case_id = make_case("ownerflow", "draft")
    response = client.post(f"/api/cases/{review_case_id}/submit", headers=auth("ownerflow"))
    assert_status(response, 200)

    response = client.post(
        f"/api/reviews/{review_case_id}",
        data={"comment": "normal user cannot review", "status": "reject"},
        headers=auth("ownerflow"),
    )
    assert_status(response, 403)

    response = client.post(
        f"/api/reviews/{review_case_id}",
        data={"comment": "需要补充教学反馈", "status": "reject"},
        headers=auth("adminflow"),
    )
    assert_status(response, 200)

    stored = get_db().cases.find_one({"id": review_case_id})
    assert stored["status"] == "needs_revision"

    response = client.get(f"/api/reviews/{review_case_id}", headers=auth("otherflow"))
    assert_status(response, 403)

    response = client.get(f"/api/reviews/{review_case_id}", headers=auth("ownerflow"))
    assert_status(response, 200)
    review_comments = [item["comment"] for item in response.json()["data"]]
    assert "需要补充教学反馈" in review_comments

    version_case = make_case("ownerflow", "draft")
    response = client.put(
        f"/api/cases/{version_case}",
        data={"content": "updated version content", "change_reason": "owner edit"},
        headers=auth("ownerflow"),
    )
    assert_status(response, 200)

    response = client.get(f"/api/versions/{version_case}", headers=auth("otherflow"))
    assert_status(response, 403)

    response = client.get(f"/api/versions/{version_case}", headers=auth("ownerflow"))
    assert_status(response, 200)
    versions = response.json()["data"]
    assert versions[0]["version_number"] == 2
    assert versions[0]["content"] == "updated version content"
    assert versions[0]["change_reason"] == "owner edit"
    assert versions[-1]["change_reason"] == "Initial creation"

    stats_visible_case = create_case(
        {
            "title": "stats visible case",
            "type": "TYPE_STATS_PUBLIC",
            "theme": "theme_stats_public",
            "content": "public statistics visible case",
            "author": "ownerflow",
            "owner_username": "ownerflow",
            "department": "test",
            "status": "approved",
            "created_at": "2030-01-01 08:00:00",
            "updated_at": "2030-01-01 08:00:00",
            "view_count": 3,
            "like_count": 4,
        }
    )
    stats_hidden_case = create_case(
        {
            "title": "stats hidden case",
            "type": "TYPE_STATS_PUBLIC",
            "theme": "theme_stats_public",
            "content": "public statistics hidden case",
            "author": "ownerflow",
            "owner_username": "ownerflow",
            "department": "test",
            "status": "approved",
            "created_at": "2031-01-01 08:00:00",
            "updated_at": "2031-01-01 08:00:00",
            "is_hidden": True,
            "view_count": 100,
            "like_count": 100,
        }
    )
    stats_deleted_case = create_case(
        {
            "title": "stats deleted case",
            "type": "TYPE_STATS_PUBLIC",
            "theme": "theme_stats_public",
            "content": "public statistics deleted case",
            "author": "ownerflow",
            "owner_username": "ownerflow",
            "department": "test",
            "status": "approved",
            "created_at": "2032-01-01 08:00:00",
            "updated_at": "2032-01-01 08:00:00",
            "view_count": 200,
            "like_count": 200,
        }
    )
    get_db().cases.update_one({"id": stats_deleted_case}, {"$set": {"status": "deleted"}})

    response = client.get("/api/statistics")
    assert_status(response, 200)
    stats = response.json()["data"]
    assert stats["by_type"]["TYPE_STATS_PUBLIC"] == 1
    assert stats["by_theme"]["theme_stats_public"] == 1
    assert stats["total_views"] == 3
    assert stats["total_likes"] == 4

    response = client.get("/api/trending?limit=20")
    assert_status(response, 200)
    trending_ids = [item["id"] for item in response.json()["data"]]
    assert stats_visible_case in trending_ids
    assert stats_hidden_case not in trending_ids
    assert stats_deleted_case not in trending_ids

    response = client.get("/api/latest?limit=20")
    assert_status(response, 200)
    latest_ids = [item["id"] for item in response.json()["data"]]
    assert stats_visible_case in latest_ids
    assert stats_hidden_case not in latest_ids
    assert stats_deleted_case not in latest_ids

    print("submit flow checks passed")


if __name__ == "__main__":
    try:
        main_test()
    finally:
        get_mongo_client().drop_database(os.environ["MONGODB_DB_NAME"])
