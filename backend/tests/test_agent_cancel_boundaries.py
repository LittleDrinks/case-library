"""Issue281 取消与失权运行边界：生成中、提交边界、重复取消、重放与后续运行。

公共 HTTP/Run 路径控制时序：确定性 FunctionModel 提供阻塞点，取消/失权后
不再产生新的正文路径（直接写入、修订候选、AI 版本），已合法交付内容保留，
失败/取消反馈可读，线程可继续后续合法运行。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from app.modules.agent import artifacts, service, writes
from app.modules.agent.models import AgentMessage
from app.modules.agent.repository import AgentRepository
from app.modules.agent.runtime import agent
from app.modules.cases.service import CaseError

DRAFT_CASE = "c-draft-1"
PENDING_CASE = "c-pending-1"
THREAD_PATH = f"/api/cases/{DRAFT_CASE}/agent/thread"
ADMIN = {"username": "admin", "password": "admin123"}
AUTHOR = {"username": "user", "password": "user123"}

DRAFT_BLOCKS = [
    {"type": "heading", "level": 1, "text": "取消边界初稿"},
    {"type": "paragraph", "text": "段落"},
]


def _login(client: TestClient, account: dict = AUTHOR) -> dict:
    response = client.post("/api/auth/login", json=account)
    assert response.status_code == 200
    return response.json()


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _post_body(text: str) -> dict:
    return {
        "id": f"browser-{uuid.uuid4().hex}", "trigger": "submit-message",
        "messages": [{"id": f"cancel-{uuid.uuid4().hex}", "role": "user",
                      "parts": [{"type": "text", "text": text}]}],
    }


def _post(client: TestClient, auth: dict, thread_id: str, text: str,
          case_id: str = DRAFT_CASE):
    return client.post(
        f"/api/cases/{case_id}/agent/thread/{thread_id}/stream",
        headers=_csrf(auth), json=_post_body(text),
    )


def _thread_id(client: TestClient, case_id: str = DRAFT_CASE,
               mode: str | None = None) -> str:
    params = {"mode": mode} if mode else None
    response = client.get(f"/api/cases/{case_id}/agent/thread", params=params)
    assert response.status_code == 200
    return response.json()["id"]


def _post_async(app, account: dict, thread_id: str, model,
                case_id: str = DRAFT_CASE, mode: str | None = None):
    """在独立线程发起流式请求：TestClient/httpx 不允许跨线程共享连接，
    子线程内建独立 client 并重新登录（与 lifecycle 测试同一形状）。"""
    def send():
        fresh = TestClient(app)
        auth = _login(fresh, account)
        with agent.override(model=model):
            return _post(fresh, auth, thread_id, "取消边界", case_id)

    pool = ThreadPoolExecutor(max_workers=1)
    return pool.submit(send), pool


def _text_model(text: str):
    """纯文本回答模型：不带工具调用（TestModel 默认会调 propose_document）。"""
    return TestModel(custom_output_text=text, call_tools=[])


def _gated_model(reached: Event | None, release: Event, *texts: str):
    """确定性阻塞模型：产出前置文本后阻塞，release 后产出收尾文本。"""
    head, tail = (texts or ("前半", "后半"))

    async def stream(_messages, _info):
        yield head
        if reached:
            reached.set()
        await asyncio.to_thread(release.wait, 30)
        yield tail

    return FunctionModel(stream_function=stream)


def _await_run(database, thread_id: str, deadline: float = 10) -> dict | None:
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        run = database.agent_runs.find_one(
            {"threadId": thread_id, "status": {"$ne": "active"}},
            {"_id": 0}, sort=[("startedAt", -1), ("id", -1)],
        )
        if run:
            return run
        Event().wait(0.02)
    return None


def _await_active(database, thread_id: str, deadline: float = 10) -> dict:
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        run = database.agent_runs.find_one(
            {"threadId": thread_id, "status": "active"}, {"_id": 0}
        )
        if run:
            return run
        Event().wait(0.02)
    raise AssertionError("run did not become active")


def _events(database, thread_id: str) -> list[dict]:
    return list(database.agent_thread_events.find(
        {"threadId": thread_id}, {"_id": 0}
    ).sort("eventSeq", 1))


def _sse_chunks(response) -> list:
    return [json.loads(line[6:]) for line in response.text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"]


def _start_review(client: TestClient) -> dict:
    from tests.test_case_workflow import _transition_json, login

    with TestClient(client.app) as admin_client:
        auth = login(admin_client).json()
        case = admin_client.get(f"/api/cases/{PENDING_CASE}").json()
        result = _transition_json(admin_client, PENDING_CASE, auth["csrfToken"],
                                  "start", case)
    assert result["case"]["workflowStatus"] == "reviewing"
    return result["case"]


def _review_thread(client: TestClient):
    _login(client, ADMIN)
    return _thread_id(client, PENDING_CASE, mode="review"), client.app.state.database


def _cancel_and_await(client: TestClient, auth: dict, thread_id: str,
                      case_id: str = DRAFT_CASE) -> dict:
    path = f"/api/cases/{case_id}/agent/thread/{thread_id}/cancel"
    stopped = client.post(path, headers=_csrf(auth))
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "cancelling"
    run = _await_run(client.app.state.database, thread_id)
    assert run is not None and run["status"] == "cancelled", run
    return run


def _shutdown(future, pool, release: Event) -> None:
    release.set()
    future.result(timeout=30)
    pool.shutdown()


def _assert_no_assistant(database, thread_id: str) -> None:
    assert database.agent_messages.count_documents(
        {"threadId": thread_id, "role": "assistant"}) == 0


def _assert_review_cancelled(database, thread_id: str, run) -> None:
    assert run is not None and run["status"] == "cancelled", run
    _assert_no_assistant(database, thread_id)


def test_cancel_before_generation_delivers_nothing(client: TestClient) -> None:
    auth = _login(client)
    thread_id = _thread_id(client)
    reached, release = Event(), Event()
    model = _gated_model(reached, release)
    future, pool = _post_async(client.app, AUTHOR, thread_id, model)
    try:
        assert reached.wait(10)
        _await_active(client.app.state.database, thread_id)
        run = _cancel_and_await(client, auth, thread_id)
        assert run["error"] == "运行已取消"
        _assert_no_assistant(client.app.state.database, thread_id)
    finally:
        _shutdown(future, pool, release)
    _assert_follow_up_run_completes(client, auth, thread_id)


def _assert_follow_up_run_completes(client: TestClient, auth: dict,
                                    thread_id: str) -> None:
    with agent.override(model=_text_model("重新回答")):
        response = _post(client, auth, thread_id, "再来一次")
    assert response.status_code == 200
    run = _await_run(client.app.state.database, thread_id)
    assert run["status"] == "completed", run


def _cancelled_run_with_base(client: TestClient, auth: dict, case: dict,
                             write_authorized: bool):
    database = client.app.state.database
    repository = AgentRepository(database)
    thread = repository.default_thread(case["id"], auth["user"]["id"])
    run = repository.start_run(
        thread, auth["user"]["id"], [{"type": "text", "text": "x"}], {},
        f"assistant-{uuid.uuid4().hex}", base_revision=case["revision"],
        write_authorized=write_authorized,
    )
    assert repository.request_cancel(run.id) is not None
    return database, thread, run


def test_cancel_request_freezes_document_write_path(client: TestClient) -> None:
    """取消请求一旦落库，直接写入在提交边界被拒绝；案例正文保持不变。"""
    from tests.test_agent_document_write import _create_case, _document

    auth = _login(client)
    case = _create_case(client, auth, _document("原稿保持。"))
    database, _thread, run = _cancelled_run_with_base(client, auth, case, True)
    with pytest.raises(CaseError):
        writes.apply_write(database, case["id"], run.id, "document",
                           DRAFT_BLOCKS, auth["user"], "取消后写入")
    assert database.cases.find_one({"id": case["id"]})["revision"] == 1


def test_cancel_request_freezes_document_candidate_path(client: TestClient) -> None:
    """取消请求落库后，整篇候选提议在同一提交边界被拒绝。"""
    from tests.test_agent_document_write import _create_case, _document

    auth = _login(client)
    case = _create_case(client, auth, _document())
    database, thread, run = _cancelled_run_with_base(client, auth, case, False)
    with pytest.raises(CaseError):
        artifacts.propose_document_artifact(
            database, case["id"], thread.id, run.id,
            DRAFT_BLOCKS, "取消后候选", [], auth["user"],
        )
    assert database.case_versions.count_documents(
        {"caseId": case["id"], "kind": "ai"}) == 0
    assert database.agent_artifacts.count_documents({}) == 0


# ---- 重放一致性：取消后的恢复流给出 abort 终块并以 [DONE] 收尾 ----


def test_events_replay_after_cancel_ends_with_abort(client: TestClient) -> None:
    auth = _login(client)
    thread_id = _thread_id(client)
    reached, release = Event(), Event()
    model = _gated_model(reached, release)
    future, pool = _post_async(client.app, AUTHOR, thread_id, model)
    try:
        assert reached.wait(10)
        _await_active(client.app.state.database, thread_id)
        _cancel_and_await(client, auth, thread_id)
        replay = client.get(
            f"{THREAD_PATH}/{thread_id}/events", params={"afterSeq": 0})
        chunks = _assert_cancel_replay(replay)
        assert not any(chunk.get("type") == "finish" for chunk in chunks)
    finally:
        _shutdown(future, pool, release)


def _assert_cancel_replay(replay) -> list:
    assert replay.status_code == 200
    chunks = _sse_chunks(replay)
    assert chunks[-1] == {"type": "abort", "reason": "运行已取消"}
    assert replay.text.endswith("data: [DONE]\n\n")
    return chunks


def test_cancelled_run_reports_readable_error_in_snapshot(
        client: TestClient) -> None:
    auth = _login(client)
    thread_id = _thread_id(client)
    reached, release = Event(), Event()
    model = _gated_model(reached, release)
    future, pool = _post_async(client.app, AUTHOR, thread_id, model)
    try:
        assert reached.wait(10)
        _await_active(client.app.state.database, thread_id)
        _cancel_and_await(client, auth, thread_id)
    finally:
        _shutdown(future, pool, release)
    snapshot = client.get(
        f"/api/cases/{DRAFT_CASE}/agent/threads/{thread_id}").json()
    assert snapshot["latestRun"]["status"] == "cancelled"
    assert snapshot["latestRun"]["error"] == "运行已取消"
    assert snapshot["activeRun"] is None


def test_repeated_cancel_requests_stay_idempotent(client: TestClient) -> None:
    auth = _login(client)
    thread_id = _thread_id(client)
    reached, release = Event(), Event()
    model = _gated_model(reached, release)
    future, pool = _post_async(client.app, AUTHOR, thread_id, model)
    try:
        assert reached.wait(10)
        _await_active(client.app.state.database, thread_id)
        _cancel_and_await(client, auth, thread_id)
        _assert_repeated_cancel_idle(client, auth, thread_id)
    finally:
        _shutdown(future, pool, release)


def _assert_repeated_cancel_idle(client: TestClient, auth: dict,
                                 thread_id: str) -> None:
    for _ in range(2):
        stopped = client.post(f"{THREAD_PATH}/{thread_id}/cancel",
                              headers=_csrf(auth))
        assert stopped.status_code == 200
    cancelled = [event for event in _events(
        client.app.state.database, thread_id)
        if event["type"] == "run.cancelled"]
    assert len(cancelled) == 1
    again = client.post(f"{THREAD_PATH}/{thread_id}/cancel", headers=_csrf(auth))
    assert again.json() == {"runId": None, "status": "idle"}


# ---- 审核失权：案例离开待审状态后运行撤销，不交付、不写入案例正文 ----


def test_review_run_revoked_when_case_leaves_review(client: TestClient,
                                                    monkeypatch) -> None:
    monkeypatch.setattr(service, "RUN_HEARTBEAT_SECONDS", 0.01)
    _start_review(client)
    thread_id, database = _review_thread(client)
    reached, release = Event(), Event()
    model = _gated_model(reached, release)
    future, pool = _post_async(client.app, ADMIN, thread_id, model, PENDING_CASE)
    try:
        assert reached.wait(10)
        _await_active(database, thread_id)
        _withdraw_pending_case(client.app)
        run = _await_run(database, thread_id)
        _assert_review_cancelled(database, thread_id, run)
        assert database.case_versions.count_documents(
            {"caseId": PENDING_CASE, "kind": "ai"}) == 0
    finally:
        _shutdown(future, pool, release)


def test_review_run_revoked_when_admin_demoted(client: TestClient,
                                               monkeypatch) -> None:
    monkeypatch.setattr(service, "RUN_HEARTBEAT_SECONDS", 0.01)
    _start_review(client)
    admin = _login(client, ADMIN)
    thread_id = _thread_id(client, PENDING_CASE, mode="review")
    database = client.app.state.database
    reached, release = Event(), Event()
    model = _gated_model(reached, release)
    future, pool = _post_async(client.app, ADMIN, thread_id, model, PENDING_CASE)
    try:
        assert reached.wait(10)
        _await_active(database, thread_id)
        database.users.update_one(
            {"id": admin["user"]["id"]}, {"$set": {"role": "user"}})
        run = _await_run(database, thread_id)
        _assert_review_cancelled(database, thread_id, run)
    finally:
        _shutdown(future, pool, release)


def test_review_completion_blocked_after_case_leaves_review(
        client: TestClient, monkeypatch) -> None:
    """提交边界竞态：完成事务与撤回并发，围栏失配按取消收敛。"""
    monkeypatch.setattr(service, "RUN_HEARTBEAT_SECONDS", 0.01)
    _start_review(client)
    admin = _login(client, ADMIN)
    thread_id = _thread_id(client, PENDING_CASE, mode="review")
    database = client.app.state.database
    _patch_withdraw_before_complete(database, monkeypatch)
    with agent.override(model=_text_model("审核意见")):
        response = _post(client, admin, thread_id, "审核请求", PENDING_CASE)
    assert response.status_code == 200
    run = _await_run(database, thread_id)
    assert run is not None and run["status"] == "cancelled", run
    _assert_no_assistant(database, thread_id)


def _patch_withdraw_before_complete(database, monkeypatch) -> None:
    from app.modules.agent.repository import AgentRepository as Repo

    original = Repo.complete_run

    def _leave_then_complete(repo_self, run_id, *args, **kwargs):
        database.cases.update_one(
            {"id": PENDING_CASE},
            {"$set": {"workflowStatus": "draft"},
             "$unset": {"reviewStartedAt": "", "submittedVersionId": ""}},
        )
        return original(repo_self, run_id, *args, **kwargs)

    monkeypatch.setattr(Repo, "complete_run", _leave_then_complete)


def test_review_run_rebased_then_completed_is_cancelled(
        client: TestClient) -> None:
    """撤回再提交后，旧审核 Run 锁定的提交基线失效，完成收敛为取消。"""
    _start_review(client)
    admin = _login(client, ADMIN)
    database = client.app.state.database
    repository, run = _locked_review_run(database, admin)
    _withdraw_pending_case(client.app)
    _resubmit_pending(client)
    assert repository.complete_run(
        run.id, _assistant_message_for(run), review_case_id=PENDING_CASE)
    row = database.agent_runs.find_one({"id": run.id}, {"_id": 0})
    assert row["status"] == "cancelled", row
    assert database.agent_messages.count_documents(
        {"threadId": run.thread_id, "role": "assistant"}) == 0


def _withdraw_pending_case(app) -> None:
    from tests.test_case_workflow import _transition_json, login

    with TestClient(app) as author_client:
        author_auth = login(author_client, "user", "user123").json()
        case = author_client.get(f"/api/cases/{PENDING_CASE}").json()
        result = _transition_json(
            author_client, PENDING_CASE, author_auth["csrfToken"], "withdraw", case)
    assert result["case"]["workflowStatus"] == "draft"


def _resubmit_pending(client: TestClient) -> None:
    from tests.test_case_workflow import _transition_json, login

    with TestClient(client.app) as author_client:
        author_auth = login(author_client, "user", "user123").json()
        case = author_client.get(f"/api/cases/{PENDING_CASE}").json()
        result = _transition_json(
            author_client, PENDING_CASE, author_auth["csrfToken"], "submit", case)
    assert result["case"]["workflowStatus"] == "pending"


def _locked_review_run(database, auth: dict):
    repository = AgentRepository(database)
    case = database.cases.find_one({"id": PENDING_CASE})
    thread = repository.default_thread(PENDING_CASE, auth["user"]["id"],
                                       mode="review")
    run = repository.start_run(
        thread, auth["user"]["id"], [{"type": "text", "text": "审核"}], {},
        f"assistant-{uuid.uuid4().hex}",
        submitted_version_id=case.get("submittedVersionId"),
    )
    return repository, run


def _assistant_message_for(run) -> AgentMessage:
    return AgentMessage(
        id=run.assistant_message_id, thread_id=run.thread_id, run_id=run.id,
        role="assistant", parts=[{"type": "text", "text": "过期审核意见"}],
        created_at=datetime.now(UTC),
    )
