#!/usr/bin/env python3
"""Executable submit-flow safety checks."""

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

os.environ["MONGODB_DB_NAME"] = f"case_library_submit_flow_test_{uuid4().hex}"
os.environ["CORS_ALLOW_ORIGINS"] = "http://127.0.0.1:18080,http://localhost:18080"

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import main
import services.public as public_service
from database import (
    create_case,
    create_user,
    get_case,
    get_db,
    get_mongo_client,
    get_statistics,
    get_user_by_username,
    increment_like_count,
    invalidate_statistics_cache,
    update_case,
)
from fastapi.testclient import TestClient

client = TestClient(main.app)


def auth(username: str):
    user = get_user_by_username(username)
    assert user, username
    return {
        "Authorization": (
            f"Bearer {main.create_auth_token(username, user.get('token_version', 0))}"
        )
    }


def bearer(token: str):
    return {"Authorization": f"Bearer {token}"}


def make_case(owner: str, status: str = "draft") -> int:
    return create_case(
        {
            "title": f"{owner}-{status}",
            "type": "TYPE_A",
            "theme": "test",
            "content": "submit flow test",
            "source_material": "source material test",
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


def assert_public_case_payload(item: dict):
    forbidden = {
        "ai_reviews",
        "ai_review",
        "admin_comments",
        "paragraph_comments",
        "prompt",
        "prompt_id",
        "model",
        "latest_review_version_id",
        "submitted_version_id",
        "reviewed_version_id",
        "owner_username",
    }
    assert forbidden.isdisjoint(item.keys()), item


def assert_openapi_documented() -> None:
    docs = client.get("/docs")
    assert_status(docs, 200)
    assert "text/html" in docs.headers.get("content-type", "")

    response = client.get("/openapi.json")
    assert_status(response, 200)
    spec = response.json()
    paths = spec.get("paths", {})
    components = spec.get("components", {})
    schemas = components.get("schemas", {})

    required_paths = {
        "/api/auth/login",
        "/api/auth/change-password",
        "/api/prompts",
        "/api/ai/chat",
        "/api/cases",
        "/api/cases/{case_id}",
        "/api/reviews/{case_id}",
        "/api/statistics",
        "/api/constants",
    }
    assert required_paths.issubset(paths.keys()), sorted(required_paths - paths.keys())

    security_schemes = components.get("securitySchemes", {})
    assert security_schemes.get("HTTPBearer", {}).get("scheme") == "bearer"

    required_schemas = {
        "LoginResponse",
        "PromptListResponse",
        "AIChatRequest",
        "AIChatResponse",
        "CaseListResponse",
        "CaseDetailResponse",
        "ReviewListResponse",
        "StatisticsResponse",
        "ConstantsResponse",
    }
    assert required_schemas.issubset(schemas.keys()), sorted(required_schemas - schemas.keys())

    assert paths["/api/prompts"]["get"].get("security") == [{"HTTPBearer": []}]
    assert paths["/api/ai/chat"]["post"].get("security") == [{"HTTPBearer": []}]
    assert "legacy_self_check" in paths["/api/ai/chat"]["post"]["requestBody"]["content"][
        "application/json"
    ]["examples"]
    assert paths["/api/cases/{case_id}/ai-review"]["post"].get("security") == [
        {"HTTPBearer": []}
    ]
    ai_review_examples = paths["/api/cases/{case_id}/ai-review"]["post"]["requestBody"][
        "content"
    ]["application/json"]["examples"]
    assert "alpha_paragraph_review" in ai_review_examples
    assert paths["/api/cases"]["post"].get("security") == [{"HTTPBearer": []}]
    assert paths["/api/reviews/{case_id}"]["post"].get("security") == [{"HTTPBearer": []}]


def assert_cors_is_not_wildcard_with_credentials() -> None:
    response = client.options(
        "/api/constants",
        headers={
            "Origin": "http://127.0.0.1:18080",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert_status(response, 200)
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:18080"
    assert response.headers.get("access-control-allow-credentials") == "true"

    blocked = client.options(
        "/api/constants",
        headers={
            "Origin": "https://example.invalid",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert_status(blocked, 400)
    assert blocked.headers.get("access-control-allow-origin") is None


def assert_cors_wildcard_disables_credentials() -> None:
    previous = os.environ.get("CORS_ALLOW_ORIGINS")
    os.environ["CORS_ALLOW_ORIGINS"] = "*"
    try:
        options = main.build_cors_options()
    finally:
        if previous is None:
            os.environ.pop("CORS_ALLOW_ORIGINS", None)
        else:
            os.environ["CORS_ALLOW_ORIGINS"] = previous

    assert options["allow_origins"] == ["*"]
    assert options["allow_credentials"] is False


def main_test() -> None:
    assert_openapi_documented()
    assert_cors_is_not_wildcard_with_credentials()
    assert_cors_wildcard_disables_credentials()

    create_user("ownerflow", "password123", role="normal", must_change_password=False)
    create_user("otherflow", "password123", role="normal", must_change_password=False)
    create_user("adminflow", "password123", role="admin", must_change_password=False)
    create_user("forceflow", "oldpass123", role="normal", must_change_password=True)

    get_db().users.update_one({"username": "otherflow"}, {"$unset": {"token_version": ""}})
    response = client.get("/api/prompts", headers=auth("otherflow"))
    assert_status(response, 200)

    response = client.post(
        "/api/auth/login",
        data={"username": "ownerflow", "password": "password123"},
    )
    assert_status(response, 200)
    owner_old_token = response.json()["data"]["token"]

    response = client.post(
        "/api/auth/change-password",
        data={
            "username": "ownerflow",
            "old_password": "password123",
            "new_password": "ownerpass456",
        },
    )
    assert_status(response, 200)

    response = client.get("/api/prompts", headers=bearer(owner_old_token))
    assert_status(response, 401)

    response = client.post(
        "/api/auth/login",
        data={"username": "ownerflow", "password": "password123"},
    )
    assert_status(response, 401)

    response = client.post(
        "/api/auth/login",
        data={"username": "ownerflow", "password": "ownerpass456"},
    )
    assert_status(response, 200)
    owner_new_token = response.json()["data"]["token"]
    response = client.get("/api/prompts", headers=bearer(owner_new_token))
    assert_status(response, 200)

    response = client.post(
        "/api/auth/login",
        data={"username": "forceflow", "password": "oldpass123"},
    )
    assert_status(response, 200)
    assert response.json()["data"]["must_change_password"] is True
    force_old_token = response.json()["data"]["token"]

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

    response = client.get("/api/prompts", headers=bearer(force_old_token))
    assert_status(response, 401)

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
    force_new_token = response.json()["data"]["token"]
    response = client.get("/api/prompts", headers=bearer(force_new_token))
    assert_status(response, 200)

    other_case = make_case("ownerflow", "draft")
    response = client.post(f"/api/cases/{other_case}/submit", headers=auth("otherflow"))
    assert_status(response, 403)

    direct_pending_case = make_case("ownerflow", "pending_review")
    direct_pending = get_db().cases.find_one({"id": direct_pending_case})
    direct_pending_version = get_db().versions.find_one({"case_id": direct_pending_case})
    assert direct_pending.get("submitted_at")
    assert direct_pending["submitted_version_id"] == direct_pending_version["id"]

    locked_pending_case = make_case("ownerflow", "pending_review")
    response = client.put(
        f"/api/cases/{locked_pending_case}",
        data={
            "content": "owner cannot edit pending content",
            "ai_reviews": json.dumps(
                [{"prompt_id": "workflow/blocked", "name": "blocked", "answer": "blocked"}]
            ),
            "change_reason": "blocked",
        },
        headers=auth("ownerflow"),
    )
    assert_status(response, 403)
    stored_locked_pending = get_db().cases.find_one({"id": locked_pending_case})
    assert stored_locked_pending["content"] == "submit flow test"
    assert stored_locked_pending["ai_reviews"] == []

    response = client.put(
        f"/api/cases/{locked_pending_case}",
        data={"content": "admin can edit pending content", "change_reason": "admin edit"},
        headers=auth("adminflow"),
    )
    assert_status(response, 200)
    stored_locked_pending = get_db().cases.find_one({"id": locked_pending_case})
    assert stored_locked_pending["content"] == "admin can edit pending content"

    locked_approved_case = make_case("ownerflow", "approved")
    response = client.put(
        f"/api/cases/{locked_approved_case}",
        data={
            "content": "owner cannot edit approved content",
            "ai_reviews": json.dumps(
                [{"prompt_id": "workflow/blocked", "name": "blocked", "answer": "blocked"}]
            ),
            "change_reason": "blocked",
        },
        headers=auth("ownerflow"),
    )
    assert_status(response, 403)
    stored_locked_approved = get_db().cases.find_one({"id": locked_approved_case})
    assert stored_locked_approved["content"] == "submit flow test"
    assert stored_locked_approved["ai_reviews"] == []

    response = client.put(
        f"/api/cases/{locked_approved_case}",
        data={"content": "admin can edit approved content", "change_reason": "admin edit"},
        headers=auth("adminflow"),
    )
    assert_status(response, 200)
    stored_locked_approved = get_db().cases.find_one({"id": locked_approved_case})
    assert stored_locked_approved["content"] == "admin can edit approved content"

    snapshot_case = make_case("ownerflow", "draft")
    response = client.put(
        f"/api/cases/{snapshot_case}",
        data={
            "title": "approved snapshot title",
            "type": "SNAPSHOT_APPROVED_TYPE",
            "theme": "snapshot-approved-theme",
            "content": "approved snapshot content",
            "source_material": "approved snapshot source",
            "department": "snapshot department",
            "change_reason": "prepare snapshot",
        },
        headers=auth("ownerflow"),
    )
    assert_status(response, 200)
    assert update_case(
        snapshot_case,
        {"keywords": ["approved-snapshot-keyword"]},
        updated_by="ownerflow",
        change_reason="prepare snapshot keywords",
    )
    response = client.post(f"/api/cases/{snapshot_case}/submit", headers=auth("ownerflow"))
    assert_status(response, 200)
    submitted = get_db().cases.find_one({"id": snapshot_case})
    reviewed_version_id = submitted["submitted_version_id"]
    response = client.post(
        f"/api/reviews/{snapshot_case}",
        data={"comment": "approve snapshot", "status": "approved", "version_id": reviewed_version_id},
        headers=auth("adminflow"),
    )
    assert_status(response, 200)
    response = client.put(
        f"/api/cases/{snapshot_case}",
        data={
            "title": "live edited title",
            "type": "LIVE_EDITED_TYPE",
            "theme": "live-edited-theme",
            "content": "live edited content",
            "source_material": "live edited source",
            "department": "live edited department",
            "change_reason": "admin live edit",
        },
        headers=auth("adminflow"),
    )
    assert_status(response, 200)
    assert update_case(
        snapshot_case,
        {"keywords": ["live-edited-keyword"]},
        updated_by="adminflow",
        change_reason="admin live keyword edit",
    )

    response = client.get(f"/api/cases/{snapshot_case}?increment_view=false")
    assert_status(response, 200)
    public_detail = response.json()["data"]
    assert public_detail["title"] == "approved snapshot title"
    assert public_detail["type"] == "SNAPSHOT_APPROVED_TYPE"
    assert public_detail["theme"] == "snapshot-approved-theme"
    assert public_detail["content"] == "approved snapshot content"
    assert public_detail["source_material"] == "approved snapshot source"
    assert public_detail["department"] == "snapshot department"
    assert_public_case_payload(public_detail)

    response = client.get("/api/cases?status=approved")
    assert_status(response, 200)
    public_listed_snapshot = next(
        item for item in response.json()["data"] if item["id"] == snapshot_case
    )
    assert public_listed_snapshot["title"] == "approved snapshot title"
    assert "content" not in public_listed_snapshot
    assert "source_material" not in public_listed_snapshot
    assert public_listed_snapshot["department"] == "snapshot department"

    response = client.get("/api/search?q=approved%20snapshot")
    assert_status(response, 200)
    assert any(item["id"] == snapshot_case for item in response.json()["data"])
    response = client.get("/api/search?q=live%20edited")
    assert_status(response, 200)
    assert all(item["id"] != snapshot_case for item in response.json()["data"])
    response = client.get("/api/search?q=approved-snapshot-keyword")
    assert_status(response, 200)
    assert any(item["id"] == snapshot_case for item in response.json()["data"])
    response = client.get("/api/search?q=live-edited-keyword")
    assert_status(response, 200)
    assert all(item["id"] != snapshot_case for item in response.json()["data"])
    response = client.get("/api/search/advanced?type=SNAPSHOT_APPROVED_TYPE")
    assert_status(response, 200)
    assert any(item["id"] == snapshot_case for item in response.json()["data"])
    response = client.get("/api/search/advanced?type=LIVE_EDITED_TYPE")
    assert_status(response, 200)
    assert all(item["id"] != snapshot_case for item in response.json()["data"])

    ai_locked_pending = make_case("ownerflow", "pending_review")
    response = client.post(
        f"/api/cases/{ai_locked_pending}/ai-review", headers=auth("ownerflow")
    )
    assert_status(response, 403)

    ai_locked_approved = make_case("ownerflow", "approved")
    response = client.post(
        f"/api/cases/{ai_locked_approved}/ai-review", headers=auth("ownerflow")
    )
    assert_status(response, 403)

    old_ai_review_enabled = os.environ.get("AI_REVIEW_ENABLED")
    os.environ["AI_REVIEW_ENABLED"] = "false"
    try:
        # Admin can still reach AI review; disabled AI returns the stable 503 contract.
        response = client.post(
            f"/api/cases/{ai_locked_approved}/ai-review", headers=auth("adminflow")
        )
        assert_status(response, 503)

        # Draft owner can still reach AI review; disabled AI returns the stable 503 contract.
        ai_draft = make_case("ownerflow", "draft")
        response = client.post(f"/api/cases/{ai_draft}/ai-review", headers=auth("ownerflow"))
        assert_status(response, 503)
    finally:
        if old_ai_review_enabled is None:
            os.environ.pop("AI_REVIEW_ENABLED", None)
        else:
            os.environ["AI_REVIEW_ENABLED"] = old_ai_review_enabled

    # Public listing ordering: newer created_at appears before older
    older_approved = make_case("ownerflow", "draft")
    newer_approved = make_case("ownerflow", "draft")
    for case_id, title, content, created_at in (
        (older_approved, "ordering older approved", "ordering older approved content", "2020-01-01 08:00:00"),
        (newer_approved, "ordering newer approved", "ordering newer approved content", "2020-01-02 08:00:00"),
    ):
        response = client.put(
            f"/api/cases/{case_id}",
            data={
                "title": title,
                "content": content,
                "department": "test",
                "type": "TYPE_A",
                "theme": "test",
                "change_reason": "prepare ordering case",
            },
            headers=auth("ownerflow"),
        )
        assert_status(response, 200)
        get_db().cases.update_one(
            {"id": case_id},
            {"$set": {"created_at": created_at}},
        )
        response = client.post(f"/api/cases/{case_id}/submit", headers=auth("ownerflow"))
        assert_status(response, 200)
        submitted = get_db().cases.find_one({"id": case_id})
        response = client.post(
            f"/api/reviews/{case_id}",
            data={
                "comment": "approve ordering",
                "status": "approved",
                "version_id": submitted["submitted_version_id"],
            },
            headers=auth("adminflow"),
        )
        assert_status(response, 200)

    response = client.get("/api/cases?status=approved")
    assert_status(response, 200)
    approved_ids = [item["id"] for item in response.json()["data"]]
    assert newer_approved in approved_ids
    assert older_approved in approved_ids
    assert approved_ids.index(newer_approved) < approved_ids.index(older_approved)

    response = client.get("/api/search?q=ordering")
    assert_status(response, 200)
    search_ids = [item["id"] for item in response.json()["data"]]
    assert newer_approved in search_ids
    assert older_approved in search_ids
    assert search_ids.index(newer_approved) < search_ids.index(older_approved)

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

    for path, forbidden_id in [
        ("/api/search?q=submit%20flow&status=all", owner_case),
        ("/api/search/advanced?status=all&keyword=submit%20flow", owner_case),
        ("/api/search?q=ownerflow&status=rejected", admin_case),
        ("/api/search/advanced?status=rejected&keyword=ownerflow", admin_case),
    ]:
        response = client.get(path)
        assert_status(response, 200)
        assert all(item.get("id") != forbidden_id for item in response.json()["data"]), path

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

    response = client.post(f"/api/cases/{visibility_case}/like")
    assert_status(response, 404)
    hidden_after_like = get_db().cases.find_one({"id": visibility_case})
    assert hidden_after_like["like_count"] == 0

    public_list = client.get("/api/cases?status=approved")
    assert_status(public_list, 200)
    assert all(item["id"] != visibility_case for item in public_list.json()["data"])

    anonymous_all = client.get("/api/cases?status=all")
    assert_status(anonymous_all, 401)

    normal_global_queue = client.get("/api/cases?status=pending_review", headers=auth("ownerflow"))
    assert_status(normal_global_queue, 403)

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
    assert "content" not in public_listed
    assert "source_material" not in public_listed
    assert_public_case_payload(public_listed)

    response = client.post(f"/api/cases/{visibility_case}/like")
    assert_status(response, 200)
    liked_case = get_db().cases.find_one({"id": visibility_case})
    assert liked_case["like_count"] == 1

    response = client.post(f"/api/cases/{visibility_case}/unlike")
    assert_status(response, 200)
    unliked_case = get_db().cases.find_one({"id": visibility_case})
    assert unliked_case["like_count"] == 0

    draft_interaction_case = make_case("ownerflow", "draft")
    response = client.post(f"/api/cases/{draft_interaction_case}/like")
    assert_status(response, 404)
    response = client.post(f"/api/cases/{draft_interaction_case}/unlike")
    assert_status(response, 404)
    draft_after_interaction = get_db().cases.find_one({"id": draft_interaction_case})
    assert draft_after_interaction["like_count"] == 0

    get_db().cases.update_one(
        {"id": visibility_case},
        {
            "$set": {
                "owner_username": "ownerflow",
                "submitted_version_id": 123,
                "reviewed_version_id": 456,
                "latest_review_version_id": 789,
                "ai_reviews": [
                    {
                        "prompt_id": "workflow/internal",
                        "name": "internal",
                        "answer": "internal AI note",
                        "model": "qwen-plus",
                    }
                ],
            }
        },
    )
    get_db().versions.update_one(
        {"case_id": visibility_case},
        {
            "$set": {
                "ai_review": {
                    "comments": [{"paragraph_id": "p1", "message": "internal AI comment"}],
                    "summary": {"risks": ["internal risk"]},
                    "prompt": "internal prompt",
                    "model": "qwen-plus",
                },
                "admin_comments": [
                    {
                        "reviewer": "adminflow",
                        "comments": [{"paragraph_id": "p1", "message": "internal admin comment"}],
                    }
                ],
            }
        },
    )
    recommendation_case = create_case(
        {
            "title": "recommended public case",
            "type": "TYPE_A",
            "theme": "test",
            "content": "recommended public source material case",
            "source_material": "source material test",
            "author": "ownerflow",
            "owner_username": "ownerflow",
            "department": "test",
            "status": "approved",
            "created_at": "2020-01-02 08:00:00",
            "updated_at": "2020-01-02 08:00:00",
            "view_count": 9,
            "like_count": 1,
        }
    )
    get_db().cases.update_one(
        {"id": recommendation_case},
        {
            "$set": {
                "submitted_version_id": 321,
                "reviewed_version_id": 654,
                "latest_review_version_id": 987,
                "ai_reviews": [
                    {
                        "prompt_id": "workflow/recommendation-internal",
                        "answer": "internal recommendation AI note",
                        "model": "qwen-plus",
                    }
                ],
            }
        },
    )

    public_surfaces = [
        (f"/api/cases/{visibility_case}", visibility_case),
        ("/api/search?q=source%20material", visibility_case),
        ("/api/search/advanced?status=approved&type=TYPE_A&keyword=source%20material", visibility_case),
        (f"/api/recommendations/{visibility_case}?limit=20", recommendation_case),
        ("/api/trending?limit=20", visibility_case),
        ("/api/latest?limit=20", visibility_case),
    ]
    for path, expected_case_id in public_surfaces:
        response = client.get(path)
        assert_status(response, 200)
        data = response.json()["data"]
        items = data if isinstance(data, list) else [data]
        matched = [item for item in items if item.get("id") == expected_case_id]
        assert matched, path
        for item in matched:
            assert item["source_material"] == "source material test"
            assert_public_case_payload(item)

    response = client.get("/api/cases?status=approved")
    assert_status(response, 200)
    public_list_items = [
        item for item in response.json()["data"] if item.get("id") == visibility_case
    ]
    assert public_list_items
    for item in public_list_items:
        assert "content" not in item
        assert "source_material" not in item
        assert_public_case_payload(item)

    for idx in range(120):
        create_case(
            {
                "title": f"public limit clamp case {idx:03d}",
                "type": "TYPE_A",
                "theme": "test",
                "content": "public limit clamp source material",
                "source_material": "source material test",
                "author": "ownerflow",
                "owner_username": "ownerflow",
                "department": "test",
                "status": "approved",
                "created_at": f"2020-02-{(idx % 28) + 1:02d} 08:00:00",
                "updated_at": f"2020-02-{(idx % 28) + 1:02d} 08:00:00",
            }
        )

    for path in [
        "/api/cases?status=approved&limit=1000",
        "/api/search/advanced?status=approved&keyword=public%20limit%20clamp&limit=1000",
        "/api/trending?limit=1000",
        "/api/latest?limit=1000",
    ]:
        response = client.get(path)
        assert_status(response, 200)
        assert len(response.json()["data"]) <= 100, path

    get_db().cases.update_one({"id": recommendation_case}, {"$set": {"status": "deleted"}})
    get_db().cases.update_one(
        {"id": visibility_case},
        {"$set": {"view_count": 0, "like_count": 0}},
    )

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

    # Soft-delete regression: case is marked deleted, related records are kept.
    soft_delete_case = make_case("ownerflow", "draft")
    response = client.post(f"/api/cases/{soft_delete_case}/submit", headers=auth("ownerflow"))
    assert_status(response, 200)
    response = client.post(
        f"/api/reviews/{soft_delete_case}",
        data={"comment": "soft delete regression review", "status": "reject"},
        headers=auth("adminflow"),
    )
    assert_status(response, 200)
    version_count_before = get_db().versions.count_documents({"case_id": soft_delete_case})
    review_count_before = get_db().reviews.count_documents({"case_id": soft_delete_case})
    assert version_count_before >= 1
    assert review_count_before >= 1

    response = client.delete(f"/api/cases/{soft_delete_case}", headers=auth("ownerflow"))
    assert_status(response, 200)
    stats = response.json()["deleted_stats"]
    assert stats["type"] == "TYPE_A"
    assert stats["theme"] == "test"

    stored = get_db().cases.find_one({"id": soft_delete_case})
    assert stored is not None
    assert stored["status"] == "deleted"
    assert stored.get("deleted_at")
    assert stored.get("deleted_by") == "ownerflow"
    assert stored.get("updated_at") == stored.get("deleted_at")

    response = client.get(f"/api/cases/{soft_delete_case}", headers=auth("ownerflow"))
    assert_status(response, 404)
    response = client.get("/api/cases?status=deleted", headers=auth("adminflow"))
    assert_status(response, 200)
    assert all(item["id"] != soft_delete_case for item in response.json()["data"])

    assert get_case(soft_delete_case) is None
    assert get_case(soft_delete_case, include_deleted=True) is not None

    assert get_db().versions.count_documents({"case_id": soft_delete_case}) == version_count_before
    assert get_db().reviews.count_documents({"case_id": soft_delete_case}) == review_count_before
    response = client.get(f"/api/versions/{soft_delete_case}", headers=auth("ownerflow"))
    assert_status(response, 200)
    assert len(response.json()["data"]) == version_count_before
    response = client.get(f"/api/reviews/{soft_delete_case}", headers=auth("adminflow"))
    assert_status(response, 200)
    assert len(response.json()["data"]) == review_count_before
    response = client.get(f"/api/reviews/{soft_delete_case}", headers=auth("otherflow"))
    assert_status(response, 403)

    review_case_id = make_case("ownerflow", "draft")

    direct_draft_review_id = make_case("ownerflow", "draft")
    response = client.post(
        f"/api/reviews/{direct_draft_review_id}",
        data={"comment": "cannot approve draft directly", "status": "approve"},
        headers=auth("adminflow"),
    )
    assert_status(response, 400)
    stored_direct_draft = get_db().cases.find_one({"id": direct_draft_review_id})
    assert stored_direct_draft["status"] == "draft"

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
    assert versions[0]["source_material"] == "source material test"
    assert versions[0]["type"] == "TYPE_A"
    assert versions[0]["theme"] == "test"
    assert versions[0]["owner_username"] == "ownerflow"
    assert versions[0]["paragraphs"][0]["paragraph_id"] == "p1"
    assert versions[0]["change_reason"] == "owner edit"
    assert versions[-1]["change_reason"] == "初始创建"

    response = client.put(
        f"/api/cases/{version_case}",
        data={"source_material": "更新后的来源材料", "change_reason": "source update"},
        headers=auth("ownerflow"),
    )
    assert_status(response, 200)
    response = client.get(f"/api/versions/{version_case}", headers=auth("ownerflow"))
    assert_status(response, 200)
    assert response.json()["data"][0]["source_material"] == "更新后的来源材料"

    stats_visible_case = create_case(
        {
            "title": "stats visible case",
            "type": "TYPE_STATS_PUBLIC",
            "theme": "theme_stats_public",
            "content": "public statistics visible case",
            "source_material": "public source material",
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

    stats_snapshot_case = make_case("ownerflow", "draft")
    response = client.put(
        f"/api/cases/{stats_snapshot_case}",
        data={
            "title": "statistics snapshot case",
            "type": "TYPE_STATS_REVIEWED",
            "theme": "theme_stats_reviewed",
            "content": "statistics snapshot content",
            "change_reason": "prepare statistics snapshot",
        },
        headers=auth("ownerflow"),
    )
    assert_status(response, 200)
    response = client.post(f"/api/cases/{stats_snapshot_case}/submit", headers=auth("ownerflow"))
    assert_status(response, 200)
    submitted = get_db().cases.find_one({"id": stats_snapshot_case})
    response = client.post(
        f"/api/reviews/{stats_snapshot_case}",
        data={
            "comment": "approve statistics snapshot",
            "status": "approved",
            "version_id": submitted["submitted_version_id"],
        },
        headers=auth("adminflow"),
    )
    assert_status(response, 200)
    response = client.put(
        f"/api/cases/{stats_snapshot_case}",
        data={
            "type": "TYPE_STATS_LIVE",
            "theme": "theme_stats_live",
            "change_reason": "admin live stats edit",
        },
        headers=auth("adminflow"),
    )
    assert_status(response, 200)

    response = client.get("/api/statistics")
    assert_status(response, 200)
    stats = response.json()["data"]
    assert stats["by_type"]["TYPE_STATS_REVIEWED"] == 1
    assert stats["by_theme"]["theme_stats_reviewed"] == 1
    assert "TYPE_STATS_LIVE" not in stats["by_type"]
    assert "theme_stats_live" not in stats["by_theme"]

    invalidate_statistics_cache()
    query_calls = {"count": 0}
    original_public_query_cases = public_service._public_query_cases
    try:
        def fake_public_query_cases():
            query_calls["count"] += 1
            return [
                {
                    "id": 9001,
                    "type": "TYPE_CACHE",
                    "theme": "theme_cache",
                    "view_count": 7,
                    "like_count": 8,
                }
            ]

        public_service._public_query_cases = fake_public_query_cases
        first_stats = get_statistics()
        second_stats = get_statistics()
        assert query_calls["count"] == 1
        assert first_stats == second_stats
        assert first_stats["total_cases"] == 1
        assert first_stats["total_views"] == 7
        assert first_stats["total_likes"] == 8

        second_stats["by_type"]["TYPE_CACHE"] = 99
        assert get_statistics()["by_type"]["TYPE_CACHE"] == 1

        public_service._statistics_cache["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
        refreshed_stats = get_statistics()
        assert query_calls["count"] == 2
        assert refreshed_stats["by_type"]["TYPE_CACHE"] == 1

        invalidate_statistics_cache()
        assert public_service._statistics_cache["data"] is None
        assert public_service._statistics_cache["expires_at"] is None
    finally:
        public_service._public_query_cases = original_public_query_cases
        invalidate_statistics_cache()

    _ = get_statistics()
    assert public_service._statistics_cache["data"] is not None
    assert increment_like_count(stats_visible_case) is True
    assert public_service._statistics_cache["data"] is None

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

    response = client.get("/api/prompts?category=workflow")
    assert_status(response, 401)

    old_prompt_key = os.environ.get("AI_API_KEY")
    os.environ["AI_API_KEY"] = "secret-test-key"
    try:
        response = client.get("/api/prompts?category=workflow", headers=auth("ownerflow"))
        assert_status(response, 200)
        prompt_items = response.json()["data"]
        prompt_ids = {item["id"] for item in prompt_items}
        assert {
            "workflow/completeness",
            "workflow/categorization",
            "workflow/expression",
            "workflow/score",
        }.issubset(prompt_ids)
        assert all("content" not in item for item in prompt_items)
        assert "secret-test-key" not in response.text

        response = client.get("/api/prompts?category=alpha", headers=auth("ownerflow"))
        assert_status(response, 200)
        alpha_prompt_items = response.json()["data"]
        assert [item["id"] for item in alpha_prompt_items] == ["alpha/paragraph-review"]
        assert alpha_prompt_items[0]["variables"] == [
            "title",
            "content",
            "source_material",
            "type",
            "theme",
        ]
        assert "content" not in alpha_prompt_items[0]
        assert "secret-test-key" not in response.text
    finally:
        if old_prompt_key is None:
            os.environ.pop("AI_API_KEY", None)
        else:
            os.environ["AI_API_KEY"] = old_prompt_key

    response = client.get("/api/prompts", headers=auth("ownerflow"))
    assert_status(response, 200)
    assert response.json()["data"] == []

    old_env = {
        key: os.environ.get(key)
        for key in [
            "AI_REVIEW_ENABLED",
            "AI_BASE_URL",
            "AI_API_KEY",
            "AI_MODELS",
            "AI_DEFAULT_MODEL",
            "AI_TIMEOUT_SECONDS",
        ]
    }
    old_call_chat_completion = main.call_chat_completion
    try:
        os.environ["AI_REVIEW_ENABLED"] = "false"
        os.environ["AI_BASE_URL"] = "https://example.invalid/v1"
        os.environ["AI_API_KEY"] = "secret-test-key"
        os.environ["AI_MODELS"] = "qwen-plus,qwen-turbo"
        os.environ["AI_DEFAULT_MODEL"] = "qwen-plus"
        os.environ["AI_TIMEOUT_SECONDS"] = "3"

        response = client.post(
            "/api/ai/chat",
            json={
                "prompt_id": "workflow/completeness",
                "variables": {"title": "AI 测试", "content": "内容"},
            },
            headers=auth("ownerflow"),
        )
        assert_status(response, 503)

        os.environ["AI_REVIEW_ENABLED"] = "true"

        response = client.post(
            "/api/ai/chat",
            json={"prompt_id": "workflow/completeness", "variables": {"title": "AI 测试"}},
            headers=auth("ownerflow"),
        )
        assert_status(response, 400)

        response = client.post(
            "/api/ai/chat",
            json={
                "prompt_id": "workflow/completeness",
                "variables": {"title": "AI 测试", "content": "内容"},
                "model": "not-allowed",
            },
            headers=auth("ownerflow"),
        )
        assert_status(response, 400)

        def fake_chat_completion(prompt_text, model, settings=None, *, system_content=""):
            assert model == "qwen-plus"
            assert "secret-test-key" not in prompt_text
            assert "secret-test-key" not in system_content
            return '{"pass": true, "detail": "可提交", "suggestions": []}'

        main.call_chat_completion = fake_chat_completion
        response = client.post(
            "/api/ai/chat",
            json={
                "prompt_id": "workflow/completeness",
                "variables": {"title": "AI 测试", "content": "内容完整"},
            },
            headers=auth("ownerflow"),
        )
        assert_status(response, 200)
        ai_data = response.json()
        assert ai_data["success"] is True
        assert ai_data["parsed"]["pass"] is True
        assert ai_data["parse_error"] is None
        assert "secret-test-key" not in response.text

        structured_case = create_case(
            {
                "title": "结构化 AI 审核案例",
                "type": "TYPE_A",
                "theme": "铸魂育人",
                "content": "第一段说明案例背景。\n第二段缺少来源支撑。",
                "source_material": "来源材料：学院新闻摘录。",
                "author": "ownerflow",
                "owner_username": "ownerflow",
                "department": "test",
                "status": "draft",
            }
        )

        response = client.post(f"/api/cases/{structured_case}/ai-review", json={})
        assert_status(response, 401)

        response = client.post(
            f"/api/cases/{structured_case}/ai-review",
            json={},
            headers=auth("otherflow"),
        )
        assert_status(response, 403)

        response = client.post(
            f"/api/cases/{structured_case}/ai-review",
            json={"model": 123},
            headers=auth("adminflow"),
        )
        assert_status(response, 400)
        assert response.json()["detail"] == "model 必须是字符串"

        os.environ["AI_REVIEW_ENABLED"] = "false"
        response = client.post(
            f"/api/cases/{structured_case}/ai-review",
            json={},
            headers=auth("ownerflow"),
        )
        assert_status(response, 503)
        assert response.json()["status"] == "disabled"
        os.environ["AI_REVIEW_ENABLED"] = "true"

        response = client.post(
            f"/api/cases/{structured_case}/ai-review",
            json={"model": "not-allowed"},
            headers=auth("ownerflow"),
        )
        assert_status(response, 400)
        assert response.json()["status"] == "invalid_model"

        def fake_malformed_structured_completion(prompt_text, model, settings=None, *, system_content=""):
            assert model == "qwen-plus"
            return "not json"

        main.call_chat_completion = fake_malformed_structured_completion
        response = client.post(
            f"/api/cases/{structured_case}/ai-review",
            json={},
            headers=auth("ownerflow"),
        )
        assert_status(response, 502)
        assert response.json()["status"] == "parse_failed"

        def fake_invalid_contract_completion(prompt_text, model, settings=None, *, system_content=""):
            assert model == "qwen-plus"
            return json.dumps(
                {
                    "comments": [
                        {
                            "paragraph_id": "p404",
                            "category": "source",
                            "severity": "important",
                            "message": "未知段落。",
                        }
                    ],
                    "summary": {},
                },
                ensure_ascii=False,
            )

        main.call_chat_completion = fake_invalid_contract_completion
        response = client.post(
            f"/api/cases/{structured_case}/ai-review",
            json={},
            headers=auth("ownerflow"),
        )
        assert_status(response, 422)
        assert response.json()["status"] == "invalid_contract"

        def fake_structured_completion(prompt_text, model, settings=None, *, system_content=""):
            assert model == "qwen-plus"
            user_payload = json.loads(prompt_text)
            paragraph_ids = {
                item["paragraph_id"] for item in user_payload["paragraphs"]
            }
            assert {"p1", "p2"}.issubset(paragraph_ids)
            assert "secret-test-key" not in prompt_text
            assert "secret-test-key" not in system_content
            return json.dumps(
                {
                    "comments": [
                        {
                            "paragraph_id": "p2",
                            "quote": "缺少来源支撑",
                            "category": "source",
                            "severity": "important",
                            "message": "这一段需要补充来源依据。",
                            "suggestion": "补充学院新闻或活动记录中的对应事实。",
                        }
                    ],
                    "summary": {
                        "strengths": ["结构清楚"],
                        "risks": ["来源支撑不足"],
                        "suggested_next_steps": ["补充来源后提交人工审核"],
                    },
                },
                ensure_ascii=False,
            )

        main.call_chat_completion = fake_structured_completion
        response = client.post(
            f"/api/cases/{structured_case}/ai-review",
            json={},
            headers=auth("ownerflow"),
        )
        assert_status(response, 200)
        structured_data = response.json()["data"]
        review_version = structured_data["version"]
        assert review_version["version_number"] == 2
        assert review_version["source_material"] == "来源材料：学院新闻摘录。"
        assert review_version["paragraphs"][1]["paragraph_id"] == "p2"
        assert review_version["ai_review"]["comments"][0]["paragraph_id"] == "p2"
        assert review_version["ai_review"]["comments"][0]["message"] == "这一段需要补充来源依据。"
        assert review_version["ai_review"]["summary"]["risks"] == ["来源支撑不足"]
        assert review_version["ai_review"]["summary"]["suggested_next_steps"] == [
            "补充来源后提交人工审核"
        ]
        assert structured_data["comments"][0]["category"] == "source"
        assert structured_data["summary"]["strengths"] == ["结构清楚"]

        stored_review_version = get_db().versions.find_one({"id": review_version["id"]})
        assert stored_review_version["ai_review"]["comments"][0]["paragraph_id"] == "p2"
        assert stored_review_version["ai_review"]["summary"]["strengths"] == ["结构清楚"]
        stored_case_after_ai = get_db().cases.find_one({"id": structured_case})
        assert stored_case_after_ai["latest_review_version_id"] == review_version["id"]
        assert stored_case_after_ai["ai_reviews"][0]["parsed"]["comments"][0]["paragraph_id"] == "p2"

        response = client.post(
            f"/api/cases/{structured_case}/submit",
            data={"version_id": review_version["id"]},
            headers=auth("ownerflow"),
        )
        assert_status(response, 200)
        stored = get_db().cases.find_one({"id": structured_case})
        assert stored["submitted_version_id"] == review_version["id"]

        invalid_review_payloads = [
            (
                {"paragraph_comments": "not-json"},
                "paragraph_comments must be valid JSON",
            ),
            (
                {
                    "paragraph_comments": json.dumps(
                        [{"paragraph_id": "p404", "message": "未知段落"}],
                        ensure_ascii=False,
                    )
                },
                "Unknown paragraph_id: p404",
            ),
            (
                {
                    "paragraph_comments": json.dumps(
                        [{"paragraph_id": "p2", "message": "  "}],
                        ensure_ascii=False,
                    )
                },
                "paragraph_comments records require message",
            ),
        ]
        for extra_payload, expected_detail in invalid_review_payloads:
            response = client.post(
                f"/api/reviews/{structured_case}",
                data={
                    "comment": "无效批注测试",
                    "status": "rejected",
                    "version_id": review_version["id"],
                    **extra_payload,
                },
                headers=auth("adminflow"),
            )
            assert_status(response, 400)
            assert response.json()["detail"] == expected_detail
            stored = get_db().cases.find_one({"id": structured_case})
            assert stored["status"] == "pending_review"

        paragraph_comments = [
            {
                "paragraph_id": "p2",
                "category": "source",
                "severity": "important",
                "message": "请补充新闻链接或原始活动记录。",
                "suggestion": "把来源材料中的时间、地点和参与对象补齐。",
            }
        ]
        response = client.post(
            f"/api/reviews/{structured_case}",
            data={
                "comment": "退回修改：来源材料不足",
                "status": "rejected",
                "version_id": review_version["id"],
                "paragraph_comments": json.dumps(paragraph_comments, ensure_ascii=False),
            },
            headers=auth("adminflow"),
        )
        assert_status(response, 200)
        stored = get_db().cases.find_one({"id": structured_case})
        assert stored["status"] == "needs_revision"
        assert stored["reviewed_version_id"] == review_version["id"]
        stored_review = get_db().reviews.find_one(
            {"case_id": structured_case, "status": "rejected"},
            sort=[("id", -1)],
        )
        assert stored_review["version_id"] == review_version["id"]
        assert stored_review["paragraph_comments"][0]["paragraph_id"] == "p2"

        response = client.get(f"/api/versions/{structured_case}", headers=auth("ownerflow"))
        assert_status(response, 200)
        latest_review_version = next(
            item for item in response.json()["data"] if item["id"] == review_version["id"]
        )
        assert latest_review_version["admin_comments"][0]["comments"][0]["paragraph_id"] == "p2"

        response = client.put(
            f"/api/cases/{structured_case}",
            data={
                "content": "第一段说明案例背景。\n第二段已经补充来源支撑。",
                "source_material": "来源材料：学院新闻摘录；活动记录补充。",
                "change_reason": "按人工审核意见补充来源材料",
            },
            headers=auth("ownerflow"),
        )
        assert_status(response, 200)
        response = client.get(f"/api/versions/{structured_case}", headers=auth("ownerflow"))
        assert_status(response, 200)
        revision_version = response.json()["data"][0]
        assert revision_version["id"] != review_version["id"]
        assert revision_version["content"] == "第一段说明案例背景。\n第二段已经补充来源支撑。"
        assert revision_version["source_material"] == "来源材料：学院新闻摘录；活动记录补充。"
        assert revision_version["change_reason"] == "按人工审核意见补充来源材料"

        response = client.post(f"/api/cases/{structured_case}/submit", headers=auth("ownerflow"))
        assert_status(response, 200)
        stored = get_db().cases.find_one({"id": structured_case})
        assert stored["status"] == "pending_review"
        assert stored["submitted_version_id"] == revision_version["id"]

        get_db().cases.update_one(
            {"id": structured_case},
            {
                "$set": {
                    "status": "approved",
                    "is_approved": True,
                    "is_in_library": True,
                }
            },
        )
        response = client.get(f"/api/cases/{structured_case}")
        assert_status(response, 200)
        public_detail = response.json()["data"]
        assert public_detail["source_material"] == "来源材料：学院新闻摘录。"
        assert_public_case_payload(public_detail)
        response = client.get(f"/api/reviews/{structured_case}")
        assert_status(response, 403)
        response = client.get(f"/api/versions/{structured_case}")
        assert_status(response, 403)
    finally:
        main.call_chat_completion = old_call_chat_completion
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    ai_review_records = [
        {
            "prompt_id": "workflow/completeness",
            "name": "完整性检查",
            "answer": "ok",
            "parsed": {"pass": True, "detail": "完整", "suggestions": []},
            "parse_error": None,
            "reviewed_at": "2026-01-01 10:00:00",
        },
        {
            "prompt_id": "workflow/expression",
            "name": "表达检查",
            "answer": "needs polish",
            "parsed": {"pass": False, "detail": "需润色", "suggestions": ["压缩标题"]},
            "parse_error": None,
            "reviewed_at": "2026-01-01 10:01:00",
        },
    ]
    response = client.post(
        "/api/cases",
        data={
            "title": "AI review persistence",
            "content": "AI review persistence content",
            "department": "test",
            "type": "TYPE_A",
            "theme": "铸魂育人",
            "status": "draft",
            "ai_reviews": json.dumps(ai_review_records, ensure_ascii=False),
        },
        headers=auth("ownerflow"),
    )
    assert_status(response, 200)
    ai_case_id = response.json()["case_id"]
    response = client.get(f"/api/cases/{ai_case_id}", headers=auth("ownerflow"))
    assert_status(response, 200)
    stored_ai_reviews = response.json()["data"]["ai_reviews"]
    assert [item["prompt_id"] for item in stored_ai_reviews] == [
        "workflow/completeness",
        "workflow/expression",
    ]
    assert stored_ai_reviews[1]["parsed"]["suggestions"] == ["压缩标题"]

    too_many_ai_reviews = [
        {"prompt_id": f"workflow/{index}", "name": "x", "answer": "x"} for index in range(4)
    ]
    response = client.put(
        f"/api/cases/{ai_case_id}",
        data={"ai_reviews": json.dumps(too_many_ai_reviews), "change_reason": "too many"},
        headers=auth("ownerflow"),
    )
    assert_status(response, 400)

    updated_ai_reviews = [
        {
            "prompt_id": "workflow/score",
            "name": "综合评分",
            "answer": "score",
            "parsed": {"score": 82, "detail": "可提交", "suggestions": []},
        }
    ]
    response = client.put(
        f"/api/cases/{ai_case_id}",
        data={
            "ai_reviews": json.dumps(updated_ai_reviews, ensure_ascii=False),
            "change_reason": "update ai reviews",
        },
        headers=auth("ownerflow"),
    )
    assert_status(response, 200)
    response = client.get(f"/api/cases/{ai_case_id}", headers=auth("ownerflow"))
    assert_status(response, 200)
    assert response.json()["data"]["ai_reviews"][0]["prompt_id"] == "workflow/score"

    print("submit flow checks passed")


if __name__ == "__main__":
    try:
        main_test()
    finally:
        get_mongo_client().drop_database(os.environ["MONGODB_DB_NAME"])
