"""隔离与越权场景步骤。"""
from __future__ import annotations


from pydantic_ai.models.test import TestModel
from pytest_bdd import given, parsers, then, when

from app.modules.agent.runtime import agent
from tests.bdd.steps.common_steps import (
    client_of,
    csrf_headers,
    get_case,
)


def _ensure_second_teacher(ctx) -> None:
    """另一位教师账号：私人讨论隔离与权限用。"""
    from app.modules.auth.passwords import hash_password

    database = client_of(ctx).app.state.database
    database.users.update_one(
        {"id": "u-second-teacher"},
        {"$setOnInsert": {
            "id": "u-second-teacher", "username": "second", "name": "另一位教师",
            "role": "user", "status": "active", "must_change_password": False,
            "campus_verified": True, "token_version": 0,
            "password_hash": hash_password("second-pass"),
        }}, upsert=True,
    )


def _login_persona(ctx, username: str, password: str) -> None:
    response = client_of(ctx).post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    session = response.json()
    session["cookie"] = response.headers["set-cookie"].split(";", 1)[0]
    ctx["sessions"][username] = session


def _persona_headers(ctx, username: str) -> dict:
    session = ctx["sessions"][username]
    return {"X-CSRF-Token": session["csrfToken"], "Cookie": session["cookie"]}


def _create_thread(ctx, persona: str, case_id: str, title: str | None = None):
    body = {"title": title} if title else {}
    return client_of(ctx).post(
        f"/api/cases/{case_id}/agent/threads", headers=_persona_headers(ctx, persona),
        json=body,
    )


@when(parsers.parse('另一位教师尝试在"{title}"创建AI线程'))
def second_teacher_tries_create(ctx, title):
    _ensure_second_teacher(ctx)
    _login_persona(ctx, "second", "second-pass")
    case_id = ctx["cases"][title]["id"]
    ctx["memo"]["last_response"] = _create_thread(ctx, "second", case_id)
    _login_persona(ctx, "user", "user123")


@when("教师列出自己的AI线程")
def teacher_lists_threads(ctx):
    case_id = ctx["memo"]["current_case_id"]
    ctx["memo"]["last_response"] = client_of(ctx).get(
        f"/api/cases/{case_id}/agent/threads",
        headers=_persona_headers(ctx, "user"),
    )


@then("线程列表只包含教师自己的线程")
def threads_owned_only(ctx):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 200
    rows = response.json()
    assert all(row["ownerId"] == "u-user-demo" for row in rows), rows


@given(parsers.parse('教师在该案例的线程甲中有一条待确认修订'))
def pending_artifact_in_thread_a(ctx):
    database = client_of(ctx).app.state.database
    from app.modules.agent.repository import AgentRepository
    from app.modules.agent import prosemirror
    from datetime import UTC, datetime

    repository = AgentRepository(database)
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    owner = repository.default_thread(case["id"], "u-user-demo")
    document = case["document"]
    block = prosemirror.text_blocks(document)[0]
    run_id = "run-pending-1"
    database.agent_runs.insert_one({
        "id": run_id, "threadId": owner.id, "userId": "u-user-demo",
        "userMessageId": "msg-1", "assistantMessageId": "amsg-1",
        "status": "completed", "skillBindings": [], "readOnly": False,
        "baseRevision": case["revision"], "resources": [], "toolTimings": {},
        "startedAt": datetime.now(UTC),
    })
    database.agent_artifacts.insert_one({
        "id": "artifact-pending-1", "caseId": case["id"], "threadId": owner.id,
        "runId": run_id, "status": "pending", "baseRevision": case["revision"],
        "target": {
            "from": block["start"], "to": block["end"],
            "quote": prosemirror.text_between(
                document, block["start"], block["end"]),
        },
        "replacement": "改写正文", "reason": "补充评价依据", "sources": [],
        "createdAt": datetime.now(UTC),
    })
    ctx["memo"]["pending_artifact"] = {
        "id": "artifact-pending-1", "thread_id": owner.id,
    }


@when(parsers.parse("教师通过线程乙提交该修订的采用"))
def decide_via_wrong_thread(ctx):
    case_id = ctx["memo"]["current_case_id"]
    other = client_of(ctx).post(
        f"/api/cases/{case_id}/agent/threads", headers=csrf_headers(ctx, "教师"),
        json={"title": "线程乙"},
    )
    assert other.status_code == 201, other.text
    artifact = ctx["memo"]["pending_artifact"]
    ctx["memo"]["last_response"] = client_of(ctx).post(
        f"/api/cases/{case_id}/agent/thread/{other.json()['id']}"
        f"/artifacts/{artifact['id']}/decision",
        headers=csrf_headers(ctx, "教师"), json={"decision": "accepted"},
    )


@then(parsers.parse("响应状态码为{code:d}"))
def status_code_is(ctx, code):
    assert ctx["memo"]["last_response"].status_code == code, \
        ctx["memo"]["last_response"].text


@then("修订候选仍为待确认状态")
def artifact_still_pending(ctx):
    database = client_of(ctx).app.state.database
    artifact = database.agent_artifacts.find_one(
        {"id": ctx["memo"]["pending_artifact"]["id"]})
    assert artifact["status"] == "pending", artifact


@given(parsers.parse('教师在该案例的线程中有待确认修订"改写正文"'))
def pending_artifact_generic(ctx):
    pending_artifact_in_thread_a(ctx)


@when("教师拒绝该修订")
def teacher_rejects_revision(ctx):
    case_id = ctx["memo"]["current_case_id"]
    artifact = ctx["memo"]["pending_artifact"]
    ctx["memo"]["last_response"] = client_of(ctx).post(
        f"/api/cases/{case_id}/agent/thread/{artifact['thread_id']}"
        f"/artifacts/{artifact['id']}/decision",
        headers=csrf_headers(ctx, "教师"), json={"decision": "rejected"},
    )
    assert ctx["memo"]["last_response"].status_code == 200, \
        ctx["memo"]["last_response"].text


@then(parsers.parse('案例正文保持"原始正文"且修订标记为已拒绝'))
def document_kept_revision_rejected(ctx):
    database = client_of(ctx).app.state.database
    artifact = database.agent_artifacts.find_one(
        {"id": ctx["memo"]["pending_artifact"]["id"]})
    assert artifact["status"] == "rejected", artifact
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    assert "原始正文" in str(case["document"])


@given(parsers.parse('教师在该案例的AI线程已有一轮回答'))
def one_answered_round(ctx):
    thread_id = client_of(ctx).get(
        f"/api/cases/{ctx['memo']['current_case_id']}/agent/thread",
        headers=csrf_headers(ctx, "教师"),
    ).json()["id"]
    model = TestModel(custom_output_text="私人回答", call_tools=[])
    with agent.override(model=model):
        response = client_of(ctx).post(
            f"/api/cases/{ctx['memo']['current_case_id']}"
            f"/agent/thread/{thread_id}/stream",
            headers=csrf_headers(ctx, "教师"),
            json={"id": "b-private", "trigger": "submit-message",
                  "messages": [{"id": "m-private", "role": "user",
                                "parts": [{"type": "text", "text": "私人问题"}]}]},
        )
    assert response.status_code == 200, response.text


@when("管理员请求该案例的AI线程")
def admin_reads_private_thread(ctx):
    case_id = ctx["memo"]["current_case_id"]
    ctx["memo"]["last_response"] = client_of(ctx).get(
        f"/api/cases/{case_id}/agent/thread", headers=csrf_headers(ctx, "管理员")
    )


@then(parsers.parse('管理员请求被拒绝且看不到教师线程'))
def admin_denied_private(ctx):
    assert ctx["memo"]["last_response"].status_code == 403, \
        ctx["memo"]["last_response"].text
    assert "仅案例作者" in ctx["memo"]["last_response"].json()["detail"]
