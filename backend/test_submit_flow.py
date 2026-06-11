#!/usr/bin/env python3
"""Executable submit-flow safety checks."""

import json
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
    assert paths["/api/cases"]["post"].get("security") == [{"HTTPBearer": []}]
    assert paths["/api/reviews/{case_id}"]["post"].get("security") == [{"HTTPBearer": []}]


def main_test() -> None:
    assert_openapi_documented()

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

    direct_pending_case = make_case("ownerflow", "pending_review")
    direct_pending = get_db().cases.find_one({"id": direct_pending_case})
    direct_pending_version = get_db().versions.find_one({"case_id": direct_pending_case})
    assert direct_pending.get("submitted_at")
    assert direct_pending["submitted_version_id"] == direct_pending_version["id"]

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
    assert public_listed["source_material"] == "source material test"
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
        ("/api/cases?status=approved", visibility_case),
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

        def fake_chat_completion(prompt_text, model, settings=None):
            assert model == "qwen-plus"
            assert "secret-test-key" not in prompt_text
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

        def fake_malformed_structured_completion(prompt_text, model, settings=None):
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

        def fake_invalid_contract_completion(prompt_text, model, settings=None):
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

        def fake_structured_completion(prompt_text, model, settings=None):
            assert model == "qwen-plus"
            assert "p1:" in prompt_text and "p2:" in prompt_text
            assert "secret-test-key" not in prompt_text
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
        assert structured_data["comments"][0]["category"] == "source"

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

        response = client.get(f"/api/versions/{structured_case}", headers=auth("ownerflow"))
        assert_status(response, 200)
        latest_review_version = next(
            item for item in response.json()["data"] if item["id"] == review_version["id"]
        )
        assert latest_review_version["admin_comments"][0]["comments"][0]["paragraph_id"] == "p2"

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
        assert "ai_reviews" not in public_detail
        assert "latest_review_version_id" not in public_detail
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
