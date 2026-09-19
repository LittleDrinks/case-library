"""AI线程生命周期场景步骤。

模型响应通过 pydantic-ai 的 model override 注入确定性假模型，
浏览器不可见部分（模型）不参与断言，断言只面向线程快照与消息。
"""
from __future__ import annotations

import time

from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pytest_bdd import given, parsers, then, when

from app.modules.agent.runtime import agent
from tests.bdd.steps.common_steps import (
    client_of,
    create_case,
    csrf_headers,
)


def _thread_id(ctx, case_id: str) -> str:
    return client_of(ctx).get(
        f"/api/cases/{case_id}/agent/thread", headers=csrf_headers(ctx, "教师")
    ).json()["id"]


def _plain_model(text: str) -> TestModel:
    return TestModel(custom_output_text=text, call_tools=[])


def _failing_model() -> FunctionModel:
    async def stream(_messages, _info):
        raise RuntimeError("provider unavailable")
        yield "unreachable"  # pragma: no cover

    return FunctionModel(stream_function=stream)


def _send(ctx, case_id: str, text: str, message_id: str = "thread-message"):
    thread_id = _thread_id(ctx, case_id)
    return client_of(ctx).post(
        f"/api/cases/{case_id}/agent/thread/{thread_id}/stream",
        headers=csrf_headers(ctx, "教师"),
        json={"id": "browser-chat-id", "trigger": "submit-message",
              "messages": [{"id": message_id, "role": "user",
                            "parts": [{"type": "text", "text": text}]}]},
    )


def _await_run(ctx, case_id: str, deadline: float = 10) -> dict | None:
    database = client_of(ctx).app.state.database
    thread_id = _thread_id(ctx, case_id)
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        run = database.agent_runs.find_one(
            {"threadId": thread_id, "status": {"$ne": "active"}},
            sort=[("startedAt", -1), ("id", -1)],
        )
        if run:
            return run
        time.sleep(0.02)
    return None


def _snapshot(ctx, case_id: str) -> dict:
    return client_of(ctx).get(
        f"/api/cases/{case_id}/agent/thread", headers=csrf_headers(ctx, "教师")
    ).json()


@when(parsers.parse('教师在AI线程提问"{text}"'))
def teacher_asks(ctx, text):
    case_id = ctx["memo"]["current_case_id"]
    with agent.override(model=_plain_model("模拟回答：已完成分析。")):
        response = _send(ctx, case_id, text)
    assert response.status_code == 200, response.text
    run = _await_run(ctx, case_id)
    assert run and run["status"] == "completed", run


@then(parsers.parse('AI回答包含"{fragment}"'))
def answer_contains(ctx, fragment):
    snapshot = _snapshot(ctx, ctx["memo"]["current_case_id"])
    messages = snapshot["messages"]
    assistant = [m for m in messages if m["role"] == "assistant"]
    assert assistant, snapshot
    assert fragment in str(assistant[-1]["parts"])


@given(parsers.parse('教师在"{title}"的AI线程已有一轮回答'))
def thread_with_history(ctx, title):
    case_id = ctx["cases"][title]["id"]
    ctx["memo"]["current_case_id"] = case_id
    with agent.override(model=_plain_model("历史回答内容。")):
        response = _send(ctx, case_id, "之前的问题")
    assert response.status_code == 200, response.text
    assert _await_run(ctx, case_id)["status"] == "completed"


@when("教师重新打开AI线程")
def teacher_reopens_thread(ctx):
    ctx["memo"]["snapshot"] = _snapshot(ctx, ctx["memo"]["current_case_id"])


@then("线程快照包含此前的用户消息与AI回答")
def snapshot_has_history(ctx):
    messages = ctx["memo"]["snapshot"]["messages"]
    roles = [m["role"] for m in messages]
    assert roles == ["user", "assistant"], roles
    texts = ["".join(part["text"] for part in message["parts"] if part["type"] == "text")
             for message in messages]
    assert texts == ["之前的问题", "历史回答内容。"]


@when("AI正在回答时教师点击停止")
def teacher_cancels_run(ctx):
    import threading

    case_id = ctx["cases"]["停止案例"]["id"]
    ctx["memo"]["current_case_id"] = case_id
    thread_id = _thread_id(ctx, case_id)

    started = threading.Event()
    gate = threading.Event()

    async def stream(_messages, _info):
        yield "前半"
        started.set()
        await asyncio.to_thread(gate.wait, 30)
        yield "后半"

    def send():
        with agent.override(model=FunctionModel(stream_function=stream)):
            ctx["send_result"] = _send(ctx, case_id, "停止测试")

    import asyncio

    worker = threading.Thread(target=send)
    worker.start()
    assert started.wait(10), "模型未进入回答中段"

    cancelled = client_of(ctx).post(
        f"/api/cases/{case_id}/agent/thread/{thread_id}/cancel",
        headers=csrf_headers(ctx, "教师"),
    )
    assert cancelled.status_code == 200, cancelled.text
    ctx["memo"]["cancel_status"] = cancelled.json()["status"]
    gate.set()
    worker.join(30)


@then(parsers.parse('该次运行结束于"{status}"且无残留活动运行'))
def run_cancelled_cleanly(ctx, status):
    case_id = ctx["memo"]["current_case_id"]
    database = client_of(ctx).app.state.database
    thread_id = _thread_id(ctx, case_id)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        active = database.agent_runs.find_one(
            {"threadId": thread_id, "status": "active"})
        if not active:
            break
        time.sleep(0.02)
    assert active is None
    run = database.agent_runs.find_one(
        {"threadId": thread_id}, sort=[("startedAt", -1)])
    assert run["status"] == status, run


@given(parsers.parse('教师的提问在"{title}"中因服务异常失败'))
def failed_run_exists(ctx, title):
    create_case(ctx, "教师", title, "待讨论正文")
    case_id = ctx["memo"]["current_case_id"]
    with agent.override(model=_failing_model()):
        response = _send(ctx, case_id, "会失败的问题", message_id="retry-original")
    assert response.status_code == 200, response.text
    failed = _await_run(ctx, case_id)
    assert failed["status"] == "failed", failed
    database = client_of(ctx).app.state.database
    thread_id = _thread_id(ctx, case_id)
    message = database.agent_messages.find_one(
        {"threadId": thread_id, "role": "user"})
    ctx["memo"]["failed_user_message_id"] = message["id"]


@when("教师重试该条消息")
def teacher_retries(ctx):
    case_id = ctx["memo"]["current_case_id"]
    thread_id = _thread_id(ctx, case_id)
    with agent.override(model=_plain_model("重试成功回答")):
        ctx["memo"]["last_response"] = client_of(ctx).post(
            f"/api/cases/{case_id}/agent/thread/{thread_id}/stream",
            headers=csrf_headers(ctx, "教师"),
            json={"id": "browser-chat-id", "trigger": "regenerate-message",
                  "messageId": ctx["memo"]["failed_user_message_id"],
                  "messages": []},
        )
    assert ctx["memo"]["last_response"].status_code == 200, \
        ctx["memo"]["last_response"].text


@then("新的运行成功完成且引用原用户消息")
def retried_run_succeeds(ctx):
    case_id = ctx["memo"]["current_case_id"]
    retried = _await_run(ctx, case_id)
    assert retried and retried["status"] == "completed", retried
    database = client_of(ctx).app.state.database
    original = database.agent_messages.find_one(
        {"id": ctx["memo"]["failed_user_message_id"]})
    assert retried["userMessageId"] == original["id"]
    assert retried["id"] != original["runId"]
