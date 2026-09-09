"""Issue241 管理员审核只读私人 AI 对话：身份、隔离与服务端只读链路。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from app.modules.agent.runtime import agent

CASE = "c-pending-1"
DRAFT_TEXT = "学生作业中存在生成式人工智能代写痕迹"
THREAD_PATH = f"/api/cases/{CASE}/agent/thread"
THREADS_PATH = f"/api/cases/{CASE}/agent/threads"
ADMIN = {"username": "admin", "password": "admin123"}
AUTHOR = {"username": "user", "password": "user123"}


def _login(client: TestClient, account: dict) -> dict:
    response = client.post("/api/auth/login", json=account)
    assert response.status_code == 200
    return response.json()


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _start_review(client: TestClient, case_id: str = CASE) -> dict:
    """管理员对待审案例开始审核：审核对话仅在 pending/reviewing 状态可用。"""
    from tests.test_case_workflow import _transition_json, login

    with TestClient(client.app) as admin_client:
        auth = login(admin_client).json()
        case = admin_client.get(f"/api/cases/{case_id}").json()
        result = _transition_json(
            admin_client, case_id, auth["csrfToken"], "start", case
        )
    assert result["case"]["workflowStatus"] == "reviewing"
    return result["case"]


def _review_thread(client: TestClient, auth: dict, case_id: str = CASE) -> dict:
    response = client.get(
        f"/api/cases/{case_id}/agent/thread", params={"mode": "review"}
    )
    assert response.status_code == 200
    return response.json()


def _send(client: TestClient, auth: dict, thread_id: str, text: str, **params) -> object:
    return client.post(
        f"{THREAD_PATH}/{thread_id}/stream", headers=_csrf(auth),
        params=params,
        json={
            "id": "review-chat", "trigger": "submit-message",
            "messages": [{"id": "m1", "role": "user",
                          "parts": [{"type": "text", "text": text}]}],
        },
    )


def test_review_thread_binds_draft_and_isolates_identities(client: TestClient) -> None:
    _start_review(client)
    admin = _login(client, ADMIN)
    mine = _review_thread(client, admin)

    assert mine["versionId"] is None and mine["caseId"] == CASE
    assert _review_thread(client, admin)["id"] == mine["id"]
    listed = client.get(THREADS_PATH, params={"mode": "review"}).json()
    assert [item["id"] for item in listed] == [mine["id"]]
    author = _login(client, AUTHOR)
    assert client.get(THREAD_PATH, params={"mode": "review"}).status_code == 403
    assert client.get(f"{THREADS_PATH}/{mine['id']}").status_code == 404


def test_demoted_admin_cannot_restore_review_thread(client: TestClient) -> None:
    """已公开案例上恢复审核线程仍要求管理员：防降权后凭线程所有权续用。"""
    database = client.app.state.database
    database.cases.update_one(
        {"id": CASE},
        {"$set": {"workflowStatus": "reviewing", "publicationStatus": "public"}},
    )
    admin = _login(client, ADMIN)
    thread_id = _review_thread(client, admin)["id"]
    database.users.update_one(
        {"id": admin["user"]["id"]}, {"$set": {"role": "user"}}
    )
    assert client.get(f"{THREADS_PATH}/{thread_id}").status_code == 403


def _skill_reject_response(client: TestClient, auth: dict, thread_id: str) -> object:
    parts = [{"type": "text", "text": "帮我改进"},
             {"type": "data-skill", "data": {"skillId": "case-edit-skill"}}]
    return client.post(
        f"{THREAD_PATH}/{thread_id}/stream", headers=_csrf(auth),
        json={"id": "c1", "trigger": "submit-message",
              "messages": [{"id": "m1", "role": "user", "parts": parts}]},
    )


def test_review_run_is_server_side_read_only(client: TestClient) -> None:
    _start_review(client)
    admin = _login(client, ADMIN)
    thread = _review_thread(client, admin)
    assert _skill_reject_response(client, admin, thread["id"]).status_code == 422

    with agent.override(model=TestModel(custom_output_text="审核讨论回答")):
        response = _send(client, admin, thread["id"], "总结这篇待审稿的问题")
    assert response.status_code == 200
    run = client.app.state.database.agent_runs.find_one({}, {"_id": 0})
    assert run["status"] == "completed"
    assert run["readOnly"] is True and run["writeAuthorized"] is False
    assert run.get("baseRevision") is None and run.get("target") is None
    prompts = [row["id"] for row in run["resources"] if row["kind"] == "task-prompt"]
    assert prompts == ["agent/review-agent"]


def test_restored_review_thread_cannot_escalate_write(client: TestClient) -> None:
    from app.modules.agent.writes import direct_write_requested

    prompt = "我要直接写入正文，立即执行"
    assert direct_write_requested(prompt) is True
    _start_review(client)
    admin = _login(client, ADMIN)
    thread_id = _review_thread(client, admin)["id"]
    assert client.get(f"{THREADS_PATH}/{thread_id}").json()["id"] == thread_id
    with agent.override(model=TestModel(custom_output_text="只读回答")):
        response = _send(client, admin, thread_id, prompt)
    assert response.status_code == 200
    run = client.app.state.database.agent_runs.find_one({"threadId": thread_id})
    assert run["writeAuthorized"] is False and run["readOnly"] is True
    assert client.app.state.database.agent_writes.count_documents({}) == 0


def test_review_instructions_come_from_pending_draft(client: TestClient) -> None:
    seen: list[str] = []

    async def _capture(_messages, info):
        seen.append(info.instructions or "")
        yield "根据待审稿回答"

    _start_review(client)
    admin = _login(client, ADMIN)
    thread = _review_thread(client, admin)
    with agent.override(model=FunctionModel(stream_function=_capture)):
        assert _send(client, admin, thread["id"], "这篇待审稿讲什么").status_code == 200
    instructions = seen[0]
    assert "案例审核讨论助手" in instructions and DRAFT_TEXT in instructions
    assert "协助案例作者修订和撰写正文" not in instructions
