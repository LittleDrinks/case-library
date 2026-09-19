"""真实资源上的检索同步中文场景步骤。

复用既有真实资源层（参照 test_search_case_content_e2e）：真实 Meilisearch +
真实 CatalogConsumer（compose e2e search-worker 持续消费 outbox）+
既有 e2e-app HTTP 公共接口。每个角色使用各自匹配的会话与 CSRF；
每次请求断言状态码；同步以公开搜索实际结果的有限轮询为准，
超时即失败并报告最后一次响应。标题每轮唯一，命中按案例 id 与标题双重匹配。
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests
from pytest_bdd import given, parsers, then, when

SYNC_DEADLINE_SECONDS = 30
SYNC_POLL_INTERVAL = 1.0


def _app_url() -> str:
    return os.environ["SEARCH_SYNC_E2E_URL"].rstrip("/")


def _login(username: str, password: str):
    client = requests.Session()
    response = client.post(
        f"{_app_url()}/api/auth/login",
        json={"username": username, "password": password}, timeout=10,
    )
    assert response.status_code == 200, response.text
    return client, response.json()["csrfToken"]


def _create_case(client, csrf: str, title: str, text: str) -> dict:
    document = {"type": "doc", "content": [
        {"type": "heading", "attrs": {"level": 1},
         "content": [{"type": "text", "text": "一、教学说明"}]},
        {"type": "paragraph", "content": [{"type": "text", "text": text}]},
    ]}
    response = client.post(
        f"{_app_url()}/api/cases", headers={"X-CSRF-Token": csrf},
        json={"title": title, "document": document}, timeout=10,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _lifecycle(client, csrf: str, case_id: str, command: str, **extra) -> dict:
    current = client.get(f"{_app_url()}/api/cases/{case_id}", timeout=10)
    assert current.status_code == 200, current.text
    response = client.post(
        f"{_app_url()}/api/cases/{case_id}/lifecycle",
        headers={"X-CSRF-Token": csrf},
        json={"command": command,
              "revision": current.json()["revision"], **extra},
        timeout=10,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _public_search(keyword: str):
    return requests.get(
        f"{_app_url()}/api/search", params={"q": keyword, "kind": "case"},
        timeout=10,
    )


@given(parsers.parse('教师发布"{title}"并经管理员审核上线'))
def published_case_online(ctx, title):
    # 标题每轮加唯一后缀：共享索引里的历史文档不会冒充本轮命中。
    unique_title = f"{title}-{uuid.uuid4().hex[:12]}"
    teacher, teacher_csrf = _login("user", "user123")
    case = _create_case(teacher, teacher_csrf, unique_title,
                        f"{unique_title}的可检索正文")
    ctx["cases"][title] = case
    ctx["memo"]["current_case_id"] = case["id"]
    ctx["memo"]["search_title"] = unique_title
    _lifecycle(teacher, teacher_csrf, case["id"], "submit")
    admin, admin_csrf = _login("admin", "admin123")
    _lifecycle(admin, admin_csrf, case["id"], "start")
    submitted = teacher.get(f"{_app_url()}/api/cases/{case['id']}", timeout=10)
    assert submitted.status_code == 200, submitted.text
    _lifecycle(admin, admin_csrf, case["id"], "approve",
               submittedVersionId=submitted.json()["submittedVersionId"])


def _poll_search_until(ctx, title: str, expect_hit: bool) -> list[tuple[str, str]]:
    case_id = ctx["cases"][title]["id"]
    keyword = ctx["memo"]["search_title"]
    deadline = time.monotonic() + SYNC_DEADLINE_SECONDS
    last_response = None
    while time.monotonic() < deadline:
        response = _public_search(keyword)
        last_response = response
        # 目录同步期间检索可能 503，重试；其余状态在超时报告里暴露。
        if response.status_code == 200:
            rows = [(row["id"], row["title"])
                    for row in response.json()["items"]]
            hit = (case_id, keyword) in rows
            if hit == expect_hit:
                return rows
        time.sleep(SYNC_POLL_INTERVAL)
    body = last_response.text if last_response is not None else "(no response)"
    pytest.fail(
        f"检索同步超时：公开搜索未在 {SYNC_DEADLINE_SECONDS}s 内"
        f"{'出现' if expect_hit else '移除'}案例 {case_id}；"
        f"最后一次响应 status={getattr(last_response, 'status_code', '?')} "
        f"body={body[:400]}"
    )


@when(parsers.parse('检索结果稳定可见"{title}"'))
def search_until_hit(ctx, title):
    ctx["memo"]["search_hits"] = _poll_search_until(ctx, title, expect_hit=True)


@when(parsers.parse('管理员将"{title}"下线'))
def admin_offline_case(ctx, title):
    admin, admin_csrf = _login("admin", "admin123")
    _lifecycle(admin, admin_csrf, ctx["cases"][title]["id"], "hide")


@when(parsers.parse('检索结果确认消失"{title}"'))
def search_until_miss(ctx, title):
    ctx["memo"]["search_hits"] = _poll_search_until(ctx, title, expect_hit=False)


@then(parsers.parse('检索结果包含"{title}"'))
def search_hits_case(ctx, title):
    case_id = ctx["cases"][title]["id"]
    assert (case_id, ctx["memo"]["search_title"]) in ctx["memo"]["search_hits"], \
        ctx["memo"]["search_hits"]


@then(parsers.parse('检索结果不再包含"{title}"'))
def search_misses_case(ctx, title):
    case_id = ctx["cases"][title]["id"]
    assert case_id not in [row_id for row_id, _ in ctx["memo"]["search_hits"]], \
        ctx["memo"]["search_hits"]
