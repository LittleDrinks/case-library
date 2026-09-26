from __future__ import annotations

import time
import json
import uuid

from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from app.modules.agent import prosemirror


def _login(client: TestClient) -> dict:
    return client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    ).json()


def _document(text: str) -> dict:
    return {"type": "doc", "content": [{
        "type": "paragraph", "content": [{"type": "text", "text": text}],
    }]}


def _empty_document() -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": []}]}


def _create_case(client: TestClient, auth: dict, document: dict | None = None) -> dict:
    return client.post(
        "/api/cases", headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "AI版本案例", "document": document or _document("教师原稿")},
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


def _full_revision_model(targets: list[dict]) -> FunctionModel:
    next_target = 0

    async def stream(_messages, _info):
        nonlocal next_target
        if next_target < len(targets):
            target = targets[next_target]
            next_target += 1
            args = {
                "start": target["start"], "end": target["end"],
                "replacement": target["replacement"], "reason": target["reason"],
            }
            yield {0: DeltaToolCall(
                name="propose_revision", json_args=json.dumps(args),
                tool_call_id=f"full-revision-{next_target}",
            )}
            return
        yield "已为全文中需要修改的位置分别提供建议。"

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
    current = client.get(f"/api/cases/{case['id']}").json()
    block = prosemirror.text_blocks(current["document"])[0]
    step = {"stepType": "replace", "from": block["start"], "to": block["end"],
            "slice": {"content": [{"type": "text", "text": "覆盖前教师稿"}]}}
    changed = client.patch(
        f"/api/cases/{case['id']}", headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"revision": current["revision"], "document": _document("覆盖前教师稿"),
              "steps": [step]},
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
    case = _create_case(client, auth, _empty_document())
    response, thread_id = _run_message(
        client, auth, case, "请完整生成全文", "full-generation-message"
    )

    assert response.status_code == 200
    _await_completed(client.app.state.database, thread_id)
    _assert_saved_version(client, case, thread_id)


def test_full_document_revision_proposes_each_changed_paragraph(client: TestClient) -> None:
    auth = _login(client)
    document = {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "第一段现有正文。"}]},
        {"type": "paragraph", "content": [{"type": "text", "text": "第二段现有正文。"}]},
    ]}
    case = _create_case(client, auth, document)
    blocks = prosemirror.text_blocks(case["document"])
    targets = [
        {"start": block["start"], "end": block["end"],
         "replacement": replacement, "reason": reason}
        for block, replacement, reason in zip(
            blocks,
            ("第一段修改建议。", "第二段修改建议。"),
            ("补足第一段重点。", "澄清第二段表达。"),
            strict=True,
        )
    ]
    thread_id = client.get(f"/api/cases/{case['id']}/agent/thread").json()["id"]
    from app.modules.agent.runtime import agent

    with agent.override(model=_full_revision_model(targets)):
        response = client.post(
            f"/api/cases/{case['id']}/agent/thread/{thread_id}/stream",
            headers={"X-CSRF-Token": auth["csrfToken"]},
            json=_message_body("请按全文需要修改的位置分别提出建议",
                               "natural-full-revision-message"),
        )

    assert response.status_code == 200
    _await_completed(client.app.state.database, thread_id)
    assert client.get(f"/api/cases/{case['id']}").json()["document"] == case["document"]
    assert client.get(f"/api/cases/{case['id']}/history").json()["versions"] == []
    artifacts = list(client.app.state.database.agent_artifacts.find(
        {"caseId": case["id"]}, {"_id": 0}, sort=[("target.from", 1)],
    ))
    assert [item["target"]["quote"] for item in artifacts] == [
        "第一段现有正文。", "第二段现有正文。",
    ]
    assert [item["replacement"] for item in artifacts] == [
        "第一段修改建议。", "第二段修改建议。",
    ]


def test_replaying_full_generation_request_does_not_duplicate_version(
    client: TestClient,
) -> None:
    auth = _login(client)
    case = _create_case(client, auth, _empty_document())
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
    case = _create_case(client, auth, _empty_document())
    response, thread_id = _run_message(
        client, auth, case, "请完整生成全文", "overwrite-version-message"
    )
    assert response.status_code == 200
    _await_completed(client.app.state.database, thread_id)
    version = client.get(f"/api/cases/{case['id']}/history").json()["versions"][0]

    overwritten = _overwrite_version(client, auth, case, version)

    assert overwritten.status_code == 200
    assert overwritten.json()["case"]["document"] == version["document"]
