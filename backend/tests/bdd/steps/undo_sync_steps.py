"""AI直接写入撤销场景步骤。

写入/撤销走真实 HTTP 公共接口（writes/undo），断言用户可观察响应。
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pytest_bdd import given, parsers, then, when

from app.modules.agent.repository import AgentRepository
from tests.bdd.steps.common_steps import (
    client_of,
    csrf_headers,
    get_case,
    login_as,
    save_case,
)


def _thread_id(ctx, case_id: str) -> str:
    return client_of(ctx).get(
        f"/api/cases/{case_id}/agent/thread", headers=csrf_headers(ctx, "教师")
    ).json()["id"]


@given(parsers.parse('教师创建空白草稿案例"{title}"'))
def blank_draft_case(ctx, title):
    response = client_of(ctx).post(
        "/api/cases", headers=csrf_headers(ctx, "教师"),
        json={"title": title},
    )
    assert response.status_code == 200, response.text
    case = response.json()
    ctx["cases"][title] = case
    ctx["memo"]["current_case_id"] = case["id"]


@given(parsers.parse('教师在该案例的线程中有一条AI写入'))
def ai_write_exists(ctx):
    # 整篇直接写入的合法前提是真空正文：先保存为空段落文档再写入。
    database = client_of(ctx).app.state.database
    repository = AgentRepository(database)
    case_id = ctx["memo"]["current_case_id"]
    blank = {"type": "doc", "content": [{"type": "paragraph"}]}
    saved = save_case(ctx, "教师", case_id, document=blank)
    assert saved.status_code == 200, saved.text
    case = get_case(ctx, case_id)
    ctx["memo"]["document_before_write"] = case["document"]
    thread = repository.default_thread(case_id, "u-user-demo")
    run = repository.start_run(
        thread, "u-user-demo", [{"type": "text", "text": "写入"}], {},
        f"assistant-{uuid.uuid4().hex}", base_revision=case["revision"],
    )
    blocks = [
        {"type": "heading", "level": 1, "text": "AI生成标题"},
        {"type": "paragraph", "text": "AI生成的正文"},
    ]
    from app.modules.agent import writes
    from app.modules.agent.models import AgentMessage

    teacher = login_as(ctx, "教师")["user"]
    record = writes.apply_write(
        database, case_id, run.id, "document", blocks, teacher,
    )
    # 直接写入后运行即终结：提交完成事件与终态，释放线程的 activeRunId。
    repository.complete_run(
        run.id,
        AgentMessage(
            id=run.assistant_message_id if hasattr(run, "assistant_message_id")
            else f"assistant-{uuid.uuid4().hex}",
            thread_id=thread.id, run_id=run.id, role="assistant",
            parts=[{"type": "text", "text": "已完成写入"}],
            created_at=datetime.now(UTC),
        ),
        owner_id=None,
    )
    ctx["memo"]["ai_write"] = {"id": record["id"], "thread_id": thread.id}


@given(parsers.parse('教师在"{title}"已撤销一条AI写入'))
def undone_write_exists(ctx, title):
    # 复用前序"有一条AI写入"造出的同一条写入，这里不新建写入。
    teacher_undo(ctx)
    assert ctx["memo"]["last_response"].status_code == 200, \
        ctx["memo"]["last_response"].text


@when("教师撤销该写入")
def teacher_undo(ctx):
    case_id = ctx["memo"]["current_case_id"]
    write = ctx["memo"]["ai_write"]
    ctx["memo"]["revision_before_undo"] = get_case(ctx, case_id)["revision"]
    ctx["memo"]["last_response"] = client_of(ctx).post(
        f"/api/cases/{case_id}/agent/thread/{write['thread_id']}"
        f"/writes/{write['id']}/undo",
        headers=csrf_headers(ctx, "教师"),
    )


@when("教师再次撤销同一写入")
def teacher_undo_again(ctx):
    teacher_undo(ctx)


@then("正文恢复为写入前的内容且写入状态为已撤销")
def undo_restored(ctx):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 200, response.text
    assert response.json()["write"]["status"] == "undone"
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    assert case["document"] == ctx["memo"]["document_before_write"]


@then("写入状态仍为已撤销且修订号不再变化")
def undo_idempotent(ctx):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 200, response.text
    assert response.json()["write"]["status"] == "undone"
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    assert case["revision"] == ctx["memo"]["revision_before_undo"]


@then("撤销被拒绝且正文与写入保持不变")
def undo_rejected(ctx):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "正文已更新，不能撤销此写入", response.text
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    assert case["document"] == ctx["memo"]["document_after_edit"]
    assert case["revision"] == ctx["memo"]["revision_after_edit"]
    database = client_of(ctx).app.state.database
    write = database.agent_writes.find_one({"id": ctx["memo"]["ai_write"]["id"]})
    assert write["status"] == "written", write


@when(parsers.parse('教师把正文改为"撤销后的新编辑"并保存'))
def save_after_undo(ctx):
    case_id = ctx["memo"]["current_case_id"]
    case = get_case(ctx, case_id)
    ctx["memo"]["last_response"] = save_case(
        ctx, "教师", case_id, title=case["title"],
        document={
            "type": "doc",
            "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "撤销后的新编辑"}]}],
        },
    )
    assert ctx["memo"]["last_response"].status_code == 200, \
        ctx["memo"]["last_response"].text
    updated = get_case(ctx, case_id)
    ctx["memo"]["document_after_edit"] = updated["document"]
    ctx["memo"]["revision_after_edit"] = updated["revision"]
