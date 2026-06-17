#!/usr/bin/env python3
"""AI review service/job boundary checks."""

# ruff: noqa: E402

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

os.environ["MONGODB_DB_NAME"] = f"case_library_test_ai_service_{uuid4().hex[:8]}"
os.environ["CORS_ALLOW_ORIGINS"] = "http://127.0.0.1:18080,http://localhost:18080"

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

import backend.app.main as main
from backend.ai_client import AIClientError, AISettings, call_chat_completion
from backend.app.core.dependencies import call_chat_completion as dependency_call_chat_completion
from backend.app.domains.ai import service as ai_service
from backend.db.connection import get_db, get_mongo_client
from backend.repositories.cases import create_case
from backend.repositories.users import create_user
from backend.repositories.versions import get_case_versions


def _settings(*, enabled: bool = True, models: tuple[str, ...] = ("qwen-plus",)) -> AISettings:
    return AISettings(
        enabled=enabled,
        base_url="https://example.invalid/v1",
        api_key="secret-test-key",
        models=models,
        default_model=models[0] if models else "qwen-plus",
        timeout_seconds=3,
    )


def _make_request(*, model: str | None = None) -> ai_service.AIReviewRequest:
    return ai_service.AIReviewRequest(
        case_id=1,
        requested_by="reviewuser",
        requested_model=model,
        case_snapshot={
            "title": "结构化 AI 审核案例",
            "type": "TYPE_A",
            "theme": "铸魂育人",
            "content": "第一段。\n第二段。",
            "source_material": "来源材料。",
        },
        paragraphs=[
            {"paragraph_id": "p1", "text": "第一段。"},
            {"paragraph_id": "p2", "text": "第二段。"},
        ],
    )


def _assert_review_error(exc: ai_service.AIReviewResponseError, status: str, code: int) -> None:
    assert exc.status == status
    assert exc.status_code == code
    assert exc.to_body()["status"] == status


def test_prepare_ai_review_job_reports_stable_config_errors():
    try:
        ai_service.prepare_ai_review_job(_make_request(), settings=_settings(enabled=False))
        raise AssertionError("expected disabled error")
    except ai_service.AIReviewResponseError as exc:
        _assert_review_error(exc, ai_service.AI_REVIEW_ERROR_DISABLED, 503)

    try:
        ai_service.prepare_ai_review_job(_make_request(), settings=_settings(models=()))
        raise AssertionError("expected unconfigured error")
    except ai_service.AIReviewResponseError as exc:
        _assert_review_error(exc, ai_service.AI_REVIEW_ERROR_UNCONFIGURED, 503)

    try:
        ai_service.prepare_ai_review_job(
            _make_request(model="not-allowed"),
            settings=_settings(models=("qwen-plus",)),
        )
        raise AssertionError("expected invalid model error")
    except ai_service.AIReviewResponseError as exc:
        _assert_review_error(exc, ai_service.AI_REVIEW_ERROR_INVALID_MODEL, 400)


def test_ai_review_job_boundaries_parse_unavailable_and_reuse():
    job = ai_service.prepare_ai_review_job(_make_request(), settings=_settings())
    assert job.model == "qwen-plus"
    assert job.request.requested_by == "reviewuser"
    assert job.reuse_key
    assert json.loads(job.user_text)["paragraphs"][1]["paragraph_id"] == "p2"

    try:
        ai_service.parse_ai_review_answer("not json")
        raise AssertionError("expected parse failure")
    except ai_service.AIReviewResponseError as exc:
        _assert_review_error(exc, ai_service.AI_REVIEW_ERROR_PARSE_FAILED, 502)

    def unavailable_completion(prompt_text, model, settings=None, *, system_content=""):
        raise AIClientError("AI 服务暂不可用")

    try:
        ai_service.call_ai_review_model(job, call_chat_completion=unavailable_completion)
        raise AssertionError("expected unavailable error")
    except ai_service.AIReviewResponseError as exc:
        _assert_review_error(exc, ai_service.AI_REVIEW_ERROR_UNAVAILABLE, 503)

    reused = ai_service.AIReviewResult(version={"ai_review": {"comments": [], "summary": {}}})
    called = {"model": False}

    def should_not_call(prompt_text, model, settings=None, *, system_content=""):
        called["model"] = True
        return "{}"

    result = ai_service.run_ai_review_job(
        job,
        call_chat_completion=should_not_call,
        reuse_lookup=(
            lambda prepared_job: reused
            if prepared_job.reuse_key == job.reuse_key
            else None
        ),
    )
    assert result is reused
    assert called["model"] is False


def test_route_dependency_still_honors_backend_app_main_chat_completion_patch():
    captured: dict = {}

    def fake_completion(prompt_text, model, settings=None, *, system_content=""):
        captured["prompt_text"] = prompt_text
        captured["model"] = model
        captured["system_content"] = system_content
        return "{}"

    old_call_chat_completion = main.call_chat_completion
    try:
        main.call_chat_completion = fake_completion
        answer = dependency_call_chat_completion(
            "payload",
            "qwen-plus",
            settings=_settings(),
            system_content="system",
        )
    finally:
        main.call_chat_completion = old_call_chat_completion

    assert answer == "{}"
    assert captured == {
        "prompt_text": "payload",
        "model": "qwen-plus",
        "system_content": "system",
    }


def test_create_case_ai_review_persists_valid_result_and_invalid_contract():
    create_user("reviewuser", "password123", role="normal", must_change_password=False)
    case_id = create_case(
        {
            "title": "服务边界案例",
            "type": "TYPE_A",
            "theme": "铸魂育人",
            "content": "第一段。\n第二段。",
            "source_material": "来源材料。",
            "author": "reviewuser",
            "owner_username": "reviewuser",
            "department": "test",
            "status": "draft",
        }
    )
    current_user = {"username": "reviewuser", "role": "normal"}
    settings = _settings()
    request = ai_service.create_ai_review_request(
        case_id,
        payload={},
        current_user=current_user,
    )
    job = ai_service.prepare_ai_review_job(request, settings=settings)

    def invalid_contract_completion(prompt_text, model, settings=None, *, system_content=""):
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

    try:
        ai_service.run_ai_review_job(job, call_chat_completion=invalid_contract_completion)
        raise AssertionError("expected invalid contract error")
    except ai_service.AIReviewResponseError as exc:
        _assert_review_error(exc, ai_service.AI_REVIEW_ERROR_INVALID_CONTRACT, 422)

    def valid_completion(prompt_text, model, settings=None, *, system_content=""):
        payload = json.loads(prompt_text)
        assert payload["paragraphs"][0]["paragraph_id"] == "p1"
        return json.dumps(
            {
                "comments": [
                    {
                        "paragraph_id": "p2",
                        "category": "source",
                        "severity": "important",
                        "message": "需要补充来源。",
                    }
                ],
                "summary": {"risks": ["来源不足"]},
            },
            ensure_ascii=False,
        )

    result = ai_service.run_ai_review_job(job, call_chat_completion=valid_completion)
    assert result.version["case_id"] == case_id
    assert result.comments[0]["paragraph_id"] == "p2"
    assert result.summary["risks"] == ["来源不足"]


def test_ai_review_persists_prompt_snapshot_when_case_changes_before_model_returns():
    create_user("snapshotuser", "password123", role="normal", must_change_password=False)
    case_id = create_case(
        {
            "title": "快照标题",
            "type": "TYPE_A",
            "theme": "原主题",
            "content": "第一段。\n第二段。",
            "source_material": "原始材料。",
            "author": "snapshotuser",
            "owner_username": "snapshotuser",
            "department": "test",
            "status": "draft",
        }
    )
    current_user = {"username": "snapshotuser", "role": "normal"}
    request = ai_service.create_ai_review_request(case_id, payload={}, current_user=current_user)
    job = ai_service.prepare_ai_review_job(request, settings=_settings())
    db = get_db()
    db.cases.update_one(
        {"id": case_id},
        {
            "$set": {
                "title": "后续改动标题",
                "content": "后续改动内容。",
            }
        },
    )

    def valid_completion(prompt_text, model, settings=None, *, system_content=""):
        prompt_payload = json.loads(prompt_text)
        assert prompt_payload["case"]["title"] == "快照标题"
        assert prompt_payload["paragraphs"][1]["text"] == "第二段。"
        return json.dumps(
            {
                "comments": [
                    {
                        "paragraph_id": "p1",
                        "category": "logic",
                        "severity": "suggestion",
                        "message": "可补充说明。",
                    }
                ],
                "summary": {},
            },
            ensure_ascii=False,
        )

    result = ai_service.run_ai_review_job(job, call_chat_completion=valid_completion)

    assert result.version["title"] == "快照标题"
    assert result.version["content"] == "第一段。\n第二段。"
    assert [item["text"] for item in result.version["paragraphs"]] == ["第一段。", "第二段。"]


def test_ai_review_returns_missing_case_and_removes_orphan_on_concurrent_change():
    create_user("conflictuser", "password123", role="normal", must_change_password=False)
    case_id = create_case(
        {
            "title": "冲突案例",
            "type": "TYPE_A",
            "theme": "原主题",
            "content": "第一段。",
            "source_material": "原始材料。",
            "author": "conflictuser",
            "owner_username": "conflictuser",
            "department": "test",
            "status": "draft",
        }
    )
    current_user = {"username": "conflictuser", "role": "normal"}
    request = ai_service.create_ai_review_request(case_id, payload={}, current_user=current_user)
    job = ai_service.prepare_ai_review_job(request, settings=_settings())
    db = get_db()
    before_version_ids = {item["id"] for item in get_case_versions(case_id)}
    db.cases.update_one({"id": case_id}, {"$set": {"updated_at": "2099-01-01 00:00:00"}})

    def valid_completion(prompt_text, model, settings=None, *, system_content=""):
        return json.dumps(
            {
                "comments": [
                    {
                        "paragraph_id": "p1",
                        "category": "logic",
                        "severity": "suggestion",
                        "message": "可补充说明。",
                    }
                ],
                "summary": {},
            },
            ensure_ascii=False,
        )

    try:
        ai_service.run_ai_review_job(job, call_chat_completion=valid_completion)
        raise AssertionError("expected missing case after concurrent change")
    except ai_service.AIServiceHTTPError as exc:
        assert exc.status_code == 404

    after_versions = get_case_versions(case_id)
    assert {item["id"] for item in after_versions} == before_version_ids
    current = db.cases.find_one({"id": case_id})
    assert "latest_review_version_id" not in current
    assert len(current.get("ai_reviews") or []) == 0


def test_ai_review_missing_updated_at_uses_snapshot_fields_for_conflict_detection():
    create_user("legacyuser", "password123", role="normal", must_change_password=False)
    case_id = create_case(
        {
            "title": "旧数据案例",
            "type": "TYPE_A",
            "theme": "原主题",
            "content": "第一段。",
            "source_material": "原始材料。",
            "author": "legacyuser",
            "owner_username": "legacyuser",
            "department": "test",
            "status": "draft",
        }
    )
    db = get_db()
    db.cases.update_one({"id": case_id}, {"$unset": {"updated_at": ""}})
    current_user = {"username": "legacyuser", "role": "normal"}
    request = ai_service.create_ai_review_request(case_id, payload={}, current_user=current_user)
    job = ai_service.prepare_ai_review_job(request, settings=_settings())
    before_version_ids = {item["id"] for item in get_case_versions(case_id)}
    db.cases.update_one({"id": case_id}, {"$set": {"content": "并发改动内容。"}})

    def valid_completion(prompt_text, model, settings=None, *, system_content=""):
        return json.dumps(
            {
                "comments": [
                    {
                        "paragraph_id": "p1",
                        "category": "logic",
                        "severity": "suggestion",
                        "message": "可补充说明。",
                    }
                ],
                "summary": {},
            },
            ensure_ascii=False,
        )

    try:
        ai_service.run_ai_review_job(job, call_chat_completion=valid_completion)
        raise AssertionError("expected missing case after legacy concurrent change")
    except ai_service.AIServiceHTTPError as exc:
        assert exc.status_code == 404

    after_versions = get_case_versions(case_id)
    assert {item["id"] for item in after_versions} == before_version_ids
    current = db.cases.find_one({"id": case_id})
    assert "latest_review_version_id" not in current
    assert len(current.get("ai_reviews") or []) == 0


@pytest.mark.real_ai
def test_real_ai_review_smoke_parses_contract_without_logging_payloads():
    settings = AISettings.from_env()
    if not settings.enabled or not settings.configured():
        pytest.skip("real AI smoke requires explicit AI_REVIEW_ENABLED and AI provider config")

    username = f"realai_{uuid4().hex[:8]}"
    create_user(username, "password123", role="normal", must_change_password=False)
    case_id = create_case(
        {
            "title": "真实 AI 连通性合成案例",
            "type": "TYPE_A",
            "theme": "铸魂育人",
            "content": "第一段说明背景。\n第二段说明改进措施。",
            "source_material": "合成来源材料，仅用于 opt-in smoke。",
            "author": username,
            "owner_username": username,
            "department": "test",
            "status": "draft",
        }
    )
    request = ai_service.create_ai_review_request(
        case_id,
        payload={"model": settings.default_model},
        current_user={"username": username, "role": "normal"},
    )
    job = ai_service.prepare_ai_review_job(request, settings=settings)
    answer = ai_service.call_ai_review_model(job, call_chat_completion=call_chat_completion)
    parsed = ai_service.parse_ai_review_answer(answer)
    result = ai_service.persist_ai_review_result(
        job,
        parsed={"comments": [], "summary": parsed.get("summary", {})},
        raw_answer="real-ai-smoke-redacted",
    )

    assert isinstance(result.comments, list)
    assert isinstance(result.summary, dict)
    assert result.version["paragraphs"][0]["paragraph_id"] == "p1"


def main_test() -> None:
    test_prepare_ai_review_job_reports_stable_config_errors()
    test_ai_review_job_boundaries_parse_unavailable_and_reuse()
    test_route_dependency_still_honors_backend_app_main_chat_completion_patch()
    test_create_case_ai_review_persists_valid_result_and_invalid_contract()
    test_ai_review_persists_prompt_snapshot_when_case_changes_before_model_returns()
    test_ai_review_returns_missing_case_and_removes_orphan_on_concurrent_change()
    test_ai_review_missing_updated_at_uses_snapshot_fields_for_conflict_detection()
    print("AI review service boundary checks passed")


if __name__ == "__main__":
    try:
        main_test()
    finally:
        get_mongo_client().drop_database(os.environ["MONGODB_DB_NAME"])
