from __future__ import annotations

import time
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from app.modules.agent.skills import full_generation_requested


def _login(client: TestClient) -> dict:
    return client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    ).json()


def _document(text: str) -> dict:
    return {"type": "doc", "content": [{
        "type": "paragraph", "content": [{"type": "text", "text": text}],
    }]}


def _create_case(client: TestClient, auth: dict) -> dict:
    return client.post(
        "/api/cases", headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "AI版本案例", "document": _document("教师原稿")},
    ).json()


def _full_generation_model() -> FunctionModel:
    blocks = [{"type": "heading", "level": 1, "text": "AI完整稿"},
              {"type": "paragraph", "text": "AI生成正文"}]
    call = ModelResponse(parts=[ToolCallPart(
        tool_name="propose_document", args={"blocks": blocks, "reason": "完整生成"}
    )])
    issued: list[bool] = []

    async def stream(_messages, _info):
        if not issued:
            issued.append(True)
            yield {0: DeltaToolCall(
                name="propose_document", json_args=json.dumps(call.parts[0].args_as_dict()),
                tool_call_id="full-generation",
            )}
            return
        yield "已生成完整 AI 稿。"

    return FunctionModel(stream_function=stream)


def _await_completed(database, thread_id: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if database.agent_runs.find_one({"threadId": thread_id, "status": "completed"}):
            return
        time.sleep(0.02)
    raise AssertionError("AI run did not complete")


def _message_body(text: str, message_id: str) -> dict:
    return {
        "id": f"browser-{uuid.uuid4().hex}", "trigger": "submit-message",
        "messages": [{"id": message_id, "role": "user",
                       "parts": [{"type": "text", "text": text}]}],
    }


def _run_message(client: TestClient, auth: dict, case: dict, text: str, message_id: str):
    from app.modules.agent.runtime import agent

    thread_id = client.get(f"/api/cases/{case['id']}/agent/thread").json()["id"]
    with agent.override(model=_full_generation_model()):
        response = client.post(
            f"/api/cases/{case['id']}/agent/thread/{thread_id}/stream",
            headers={"X-CSRF-Token": auth["csrfToken"]},
            json=_message_body(text, message_id),
        )
    return response, thread_id


def _assert_saved_version(client: TestClient, case: dict, thread_id: str) -> None:
    history = client.get(f"/api/cases/{case['id']}/history").json()
    assert [(row["kind"], row["title"]) for row in history["versions"]] == [("ai", "AI版本案例")]
    assert history["versions"][0]["document"]["content"] == [
        {"type": "heading", "attrs": {"level": 1},
         "content": [{"type": "text", "text": "AI完整稿"}]},
        {"type": "paragraph", "content": [{"type": "text", "text": "AI生成正文"}]},
    ]
    assert client.get(f"/api/cases/{case['id']}").json()["document"] == case["document"]
    assert client.app.state.database.agent_artifacts.count_documents({}) == 0
    snapshot = client.get(f"/api/cases/{case['id']}/agent/threads/{thread_id}").json()
    tool = next(part for message in snapshot["messages"] for part in message["parts"]
                if part["type"] == "tool-propose_document")
    assert tool["output"] == {
        "status": "created", "kind": "ai", "versionId": history["versions"][0]["id"],
    }
    events = client.app.state.database.agent_thread_events.find({"threadId": thread_id})
    assert any(event["type"] == "version.created" for event in events)


def _overwrite_version(client: TestClient, auth: dict, case: dict, version: dict):
    changed = client.patch(
        f"/api/cases/{case['id']}", headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"revision": 1, "document": _document("覆盖前教师稿")},
    ).json()
    return client.post(
        f"/api/cases/{case['id']}/lifecycle",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"command": "overwrite", "revision": changed["revision"],
              "targetId": version["id"]},
    )


def test_full_generation_is_a_readonly_version_without_changing_the_draft(
    client: TestClient,
) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    response, thread_id = _run_message(
        client, auth, case, "请完整生成全文", "full-generation-message"
    )

    assert response.status_code == 200
    _await_completed(client.app.state.database, thread_id)
    _assert_saved_version(client, case, thread_id)


def test_ordinary_chat_cannot_create_an_ai_version(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    response, thread_id = _run_message(
        client, auth, case, "请分析全文", "ordinary-chat-message"
    )

    assert response.status_code == 200
    _await_completed(client.app.state.database, thread_id)
    assert client.get(f"/api/cases/{case['id']}/history").json()["versions"] == []
    assert client.app.state.database.agent_artifacts.count_documents({}) == 0


def test_natural_full_generation_request_creates_an_ai_version(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    response, thread_id = _run_message(
        client, auth, case, "请根据资料重写整个案例", "natural-full-generation-message"
    )

    assert response.status_code == 200
    _await_completed(client.app.state.database, thread_id)
    _assert_saved_version(client, case, thread_id)


def test_reverse_order_full_generation_request_creates_an_ai_version(
    client: TestClient,
) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    response, thread_id = _run_message(
        client, auth, case, "帮我把整篇案例重写一遍", "reverse-full-generation-message"
    )

    assert response.status_code == 200
    _await_completed(client.app.state.database, thread_id)
    _assert_saved_version(client, case, thread_id)


def test_full_generation_parser_rejects_non_requests() -> None:
    for prompt in (
        '请说明“生成全文”这个功能', "你会生成全文吗", "什么是全文生成",
        "请重写全文中的第二段",
        "不要生成全文", "没有让你重写全文", "请重写整个案例，但是不要生成全文",
    ):
        assert full_generation_requested(prompt) is False, prompt
    assert full_generation_requested("不要生成全文，但是请重写整个案例") is True


@pytest.mark.parametrize("prompt", [
    "把整份文档改写一遍", "将完整案例重写", "全文重写",
])
def test_full_generation_parser_accepts_natural_reverse_order(prompt: str) -> None:
    assert full_generation_requested(prompt) is True


@pytest.mark.parametrize("prompt", [
    "先别重写整篇", "千万别生成全文", "帮我整理整个文档的批注",
])
def test_full_generation_parser_rejects_natural_non_requests(prompt: str) -> None:
    assert full_generation_requested(prompt) is False


@pytest.mark.parametrize("prompt", [
    '请说明“生成全文”这个功能', "你会生成全文吗", "请重写全文中的第二段",
    "不要生成全文", "没有让你重写全文", "先别重写整篇",
    "请重写整个案例，但是不要生成全文",
])
def test_non_generation_public_runs_do_not_create_ai_versions(
    client: TestClient, prompt: str
) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    response, thread_id = _run_message(
        client, auth, case, prompt, f"non-generation-{uuid.uuid4().hex}"
    )

    assert response.status_code == 200
    _await_completed(client.app.state.database, thread_id)
    assert client.get(f"/api/cases/{case['id']}/history").json()["versions"] == []
    assert client.app.state.database.agent_artifacts.count_documents({}) == 0


def test_negated_full_generation_request_cannot_create_an_ai_version(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    response, thread_id = _run_message(
        client, auth, case, "不要生成全文", "negated-full-generation-message"
    )

    assert response.status_code == 200
    _await_completed(client.app.state.database, thread_id)
    assert not full_generation_requested("不要生成全文")
    assert client.get(f"/api/cases/{case['id']}/history").json()["versions"] == []
    assert client.app.state.database.agent_artifacts.count_documents({}) == 0


def test_replaying_full_generation_request_does_not_duplicate_version(
    client: TestClient,
) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    first, thread_id = _run_message(
        client, auth, case, "请完整生成全文", "same-user-message"
    )
    assert first.status_code == 200
    _await_completed(client.app.state.database, thread_id)
    second = client.post(
        f"/api/cases/{case['id']}/agent/thread/{thread_id}/stream",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json=_message_body("请完整生成全文", "same-user-message"),
    )

    assert second.status_code == 409
    versions = client.get(f"/api/cases/{case['id']}/history").json()["versions"]
    assert len(versions) == 1


def test_ai_version_uses_the_existing_overwrite_flow(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    response, thread_id = _run_message(
        client, auth, case, "请完整生成全文", "overwrite-version-message"
    )
    assert response.status_code == 200
    _await_completed(client.app.state.database, thread_id)
    version = client.get(f"/api/cases/{case['id']}/history").json()["versions"][0]
    overwritten = _overwrite_version(client, auth, case, version)

    assert overwritten.status_code == 200
    assert overwritten.json()["case"]["document"] == version["document"]
