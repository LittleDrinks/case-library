"""Issue22 来源权限投影回归：快照、恢复流与模型历史共用同一可见性收敛。

收紧（来源转私密）后：受影响 assistant 回答、推理、修订提议在快照、
SSE 恢复、下一轮模型历史三个输出面都不得复述来源正文；私人 Thread
与数据库原始历史保持完整。全部走真实 HTTP（TestClient → FastAPI 栈）。
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from pydantic_ai.models.function import (
    DeltaThinkingPart,
    DeltaToolCall,
    FunctionModel,
)

from app.modules.agent import agent, prosemirror
from app.modules.agent.visibility import (
    HIDDEN_ANSWER,
    HIDDEN_REVISION,
    parts_projector,
)
from app.modules.agent.source_reader import read_source

SOURCE_TEXT = "固定版本正文"
LEAK_MARK = "科学家精神原典摘句"
PROPOSE_PARAGRAPHS = ("第一段保持不变。", "第二段需要补充评价依据。")


def _document(*text: str) -> dict:
    return {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": item}]}
        for item in text
    ]}


def _auth(client: TestClient) -> dict:
    return client.post("/api/auth/login", json={"username": "user", "password": "user123"}).json()


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _seed_source(database, case_id: str = "c-draft-1", public: str = "public") -> None:
    database.cases.insert_one({
        "id": "c-source-22", "ownerId": "other", "publicationStatus": public,
        "workflowStatus": "published", "publishedVersionId": "v-source-22",
    })
    database.case_versions.insert_one({
        "id": "v-source-22", "caseId": "c-source-22", "number": 4,
        "title": "固定来源", "document": _document(SOURCE_TEXT),
    })
    database.case_sources.insert_one({
        "id": "src-22", "caseId": case_id, "sourceCaseId": "c-source-22",
        "versionId": "v-source-22", "versionNumber": 4, "title": "固定来源",
    })


def _revoke_source(database) -> None:
    database.cases.update_one(
        {"id": "c-source-22"}, {"$set": {"publicationStatus": "private"}}
    )


def _tool_delta(name: str, args: dict, call_id: str) -> dict:
    return {0: DeltaToolCall(name=name, json_args=json.dumps(args), tool_call_id=call_id)}


def _tool_names(messages) -> list[str]:
    return [
        part.tool_name for message in messages
        for part in getattr(message, "parts", [])
        if getattr(part, "part_kind", "") == "tool-call"
    ]


def _reader_then_answer(sink=None) -> FunctionModel:
    """先读固定来源，再输出复述来源正文的回答；sink 收集观察到的模型历史。"""

    async def stream(messages, _info):
        if sink is not None:
            sink.append(messages)
        if "read_source" not in _tool_names(messages):
            yield _tool_delta(
                "read_source", {"source_type": "case", "source_id": "src-22"}, "vis-read-1",
            )
            return
        yield f"依据来源：{LEAK_MARK}"

    return FunctionModel(stream_function=stream)


def _stream_body(text: str, message_id: str = "visible-message",
                 extra: list[dict] | None = None) -> dict:
    parts = [{"type": "text", "text": text}]
    parts.extend(extra or [])
    return {
        "id": f"browser-{message_id}", "trigger": "submit-message",
        "messages": [{"id": message_id, "role": "user", "parts": parts}],
    }


def _post_stream(client: TestClient, auth: dict, case_id: str, thread_id: str,
                 body: dict, model: FunctionModel):
    with agent.override(model=model):
        return client.post(
            f"/api/cases/{case_id}/agent/thread/{thread_id}/stream",
            headers=_csrf(auth), json=body,
        )


def _thread(client: TestClient, case_id: str) -> str:
    return client.get(f"/api/cases/{case_id}/agent/thread").json()["id"]


def _replay(client: TestClient, case_id: str, thread_id: str) -> str:
    with client.stream("GET", f"/api/cases/{case_id}/agent/thread/{thread_id}/events") as response:
        assert response.status_code == 200
        return "".join(response.iter_text())


def _snapshot(client: TestClient, thread_id: str, case_id: str = "c-draft-1") -> dict:
    response = client.get(f"/api/cases/{case_id}/agent/threads/{thread_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _assistant_texts(snapshot: dict) -> list[str]:
    return [
        part.get("text") or "" for message in snapshot["messages"]
        if message["role"] == "assistant" for part in message["parts"]
        if part.get("type") == "text"
    ]


def _history_texts(observed: list) -> str:
    return "".join(
        str(part) for messages in observed for message in messages
        for part in getattr(message, "parts", [])
    )


def _seeded_client(client: TestClient) -> dict:
    _seed_source(client.app.state.database)
    auth = _auth(client)
    thread_id = _thread(client, "c-draft-1")
    response = _post_stream(
        client, auth, "c-draft-1", thread_id, _stream_body("帮我读来源"),
        _reader_then_answer(),
    )
    assert response.status_code == 200, response.text
    return {"auth": auth, "thread_id": thread_id}


def test_snapshot_hides_tainted_answer_after_source_revoked(client: TestClient) -> None:
    context = _seeded_client(client)
    snapshot = _snapshot(client, context["thread_id"])
    assert LEAK_MARK in "".join(_assistant_texts(snapshot))
    _revoke_source(client.app.state.database)
    revoked = _snapshot(client, context["thread_id"])
    assert _assistant_texts(revoked) == [HIDDEN_ANSWER]
    read = next(part for message in revoked["messages"] for part in message["parts"]
                if part.get("type") == "tool-read_source")
    assert read["output"] == {"status": "no_access", "detail": "来源当前不可读"}


def test_snapshot_projection_keeps_private_thread_and_raw_history(client: TestClient) -> None:
    context = _seeded_client(client)
    database = client.app.state.database
    _revoke_source(database)
    revoked = _snapshot(client, context["thread_id"])
    roles = [message["role"] for message in revoked["messages"]]
    assert roles == ["user", "assistant"]
    assert revoked["messages"][0]["parts"][0]["text"] == "帮我读来源"
    stored = database.agent_messages.find_one(
        {"threadId": context["thread_id"], "role": "assistant"}
    )
    assert LEAK_MARK in json.dumps(stored["parts"], ensure_ascii=False)


def test_recovery_stream_applies_same_projection(client: TestClient) -> None:
    context = _seeded_client(client)
    database = client.app.state.database
    assert LEAK_MARK in _replay(client, "c-draft-1", context["thread_id"])
    _revoke_source(database)
    replayed = _replay(client, "c-draft-1", context["thread_id"])
    assert LEAK_MARK not in replayed
    assert HIDDEN_ANSWER in replayed
    assert "no_access" in replayed


def test_next_turn_model_history_excludes_revoked_source_body(client: TestClient) -> None:
    context = _seeded_client(client)
    database = client.app.state.database
    _revoke_source(database)
    observed: list = []
    response = _post_stream(
        client, context["auth"], "c-draft-1", context["thread_id"],
        _stream_body("继续讨论", "second-message"),
        _reader_then_answer(observed),
    )
    assert response.status_code == 200, response.text
    history = _history_texts(observed)
    assert LEAK_MARK not in history
    assert HIDDEN_ANSWER in history
    assert "no_access" in history
    assert "帮我读来源" in history


def _retry_second_message(client, context, retry_message_id, observed):
    async def stream(messages, _info):
        observed.append(messages)
        yield "重试回答"

    with agent.override(model=FunctionModel(stream_function=stream)):
        return client.post(
            f"/api/cases/c-draft-1/agent/thread/{context['thread_id']}/stream",
            headers=_csrf(context["auth"]),
            json={"id": "browser-retry", "trigger": "regenerate-message",
                  "messageId": retry_message_id, "messages": []},
        )


def test_retry_model_history_excludes_revoked_source_body(client: TestClient) -> None:
    context = _seeded_client(client)
    database = client.app.state.database
    _revoke_source(database)
    response = _post_stream(
        client, context["auth"], "c-draft-1", context["thread_id"],
        _stream_body("继续讨论", "second-message"), _reader_then_answer(),
    )
    assert response.status_code == 200, response.text
    observed: list = []
    retry_message_id = database.agent_messages.find_one(
        {"threadId": context["thread_id"], "role": "user"},
        sort=[("messageSeq", -1)],
    )["id"]
    retried = _retry_second_message(client, context, retry_message_id, observed)
    assert retried.status_code == 200, retried.text
    history = _history_texts(observed)
    assert LEAK_MARK not in history and HIDDEN_ANSWER in history


def test_read_source_ref_carries_structured_source_case_id(client: TestClient) -> None:
    database = client.app.state.database
    _seed_source(database)
    result = read_source(database, None, {"id": "u-user-demo", "role": "user"},
                         "c-draft-1", "case", "src-22")
    assert result["status"] == "ok"
    assert result["usedSourceRef"]["sourceCaseId"] == "c-source-22"
    assert result["usedSourceRef"]["id"] == "src-22"


def _proposal_case(client: TestClient, auth: dict) -> tuple[dict, int, int]:
    document = _document(*PROPOSE_PARAGRAPHS)
    case = client.post("/api/cases", headers=_csrf(auth), json={
        "title": "投影修订案例", "document": document,
    }).json()
    blocks = prosemirror.text_blocks(document)
    return case, blocks[1]["start"], blocks[1]["end"]


def _proposal_thread(client: TestClient, database):
    auth = _auth(client)
    case, start, end = _proposal_case(client, auth)
    _seed_source(database, case_id=case["id"])
    thread_id = _thread(client, case["id"])
    return auth, case, thread_id, start, end


def _propose_tool_call(start: int, end: int) -> dict:
    return _tool_delta("propose_revision", {
        "start": start, "end": end,
        "replacement": f"修订后仍引用{LEAK_MARK}作评价依据",
        "reason": f"理由依据{LEAK_MARK}",
    }, "vis-propose-1")


def _proposal_model(sink=None, start: int = 1, end: int = 4) -> FunctionModel:
    """读源 → 提议复述受限内容的修订 → 推理与结论均复述受限内容。"""
    state = {"phase": 0}

    async def stream(messages, _info):
        if sink is not None:
            sink.append(messages)
        called = _tool_names(messages)
        if "read_source" not in called:
            yield _tool_delta(
                "read_source", {"source_type": "case", "source_id": "src-22"}, "vis-read-2",
            )
        elif "propose_revision" not in called:
            yield _propose_tool_call(start, end)
        else:
            yield _next_proposal_answer(state)

    return FunctionModel(stream_function=stream)


def _next_proposal_answer(state: dict):
    if state["phase"] == 0:
        state["phase"] = 1
        return {0: DeltaThinkingPart(content=f"推理：{LEAK_MARK}支持该修订。")}
    return f"结论：修订引用了{LEAK_MARK}。"


def _run_proposal_turn(client, auth, case, thread_id, start, end) -> None:
    response = _post_stream(
        client, auth, case["id"], thread_id,
        _stream_body("请修订第二段", extra=[
            {"type": "data-selection", "data": {"from": start, "to": end}},
        ]),
        _proposal_model(start=start, end=end),
    )
    assert response.status_code == 200, response.text


def _assert_hidden_snapshot(revoked: dict, start: int, end: int) -> None:
    assert LEAK_MARK not in json.dumps(revoked, ensure_ascii=False)
    artifact = revoked["artifacts"][0]
    assert artifact["replacement"] == HIDDEN_REVISION
    assert artifact["reason"] == HIDDEN_REVISION
    assert artifact["sources"] == []
    parts = [part for message in revoked["messages"] if message["role"] == "assistant"
             for part in message["parts"]]
    reasoning = next(part for part in parts if part.get("type") == "reasoning")
    assert reasoning["text"] == HIDDEN_ANSWER
    propose = next(part for part in parts if part.get("type") == "tool-propose_revision")
    assert propose["input"]["replacement"] == HIDDEN_REVISION
    assert propose["input"]["reason"] == HIDDEN_REVISION
    assert propose["input"]["start"] == start and propose["input"]["end"] == end
    assert propose["output"]["replacement"] == HIDDEN_REVISION


def test_revision_reasoning_and_propose_inputs_hidden_after_revocation(
    client: TestClient,
) -> None:
    database = client.app.state.database
    auth, case, thread_id, start, end = _proposal_thread(client, database)
    _run_proposal_turn(client, auth, case, thread_id, start, end)
    baseline = json.dumps(_snapshot(client, thread_id, case["id"]), ensure_ascii=False)
    assert LEAK_MARK in baseline and "修订后仍引用" in baseline
    _revoke_source(database)
    _assert_hidden_snapshot(_snapshot(client, thread_id, case["id"]), start, end)
    assert LEAK_MARK not in _replay(client, case["id"], thread_id)


def test_proposal_model_history_excludes_revoked_revision_body(client: TestClient) -> None:
    database = client.app.state.database
    auth, case, thread_id, start, end = _proposal_thread(client, database)
    _run_proposal_turn(client, auth, case, thread_id, start, end)
    _revoke_source(database)
    observed: list = []
    response = _post_stream(
        client, auth, case["id"], thread_id,
        _stream_body("继续讨论", "third-message"),
        _reader_then_answer(observed),
    )
    assert response.status_code == 200, response.text
    assert LEAK_MARK not in _history_texts(observed)
    assert "修订后仍引用" not in _history_texts(observed)


def test_parts_projector_reverifies_permissions_per_call(client: TestClient) -> None:
    database = client.app.state.database
    _seed_source(database)
    user = {"id": "u-user-demo", "role": "user"}
    project = parts_projector(database, user, "c-draft-1")
    parts = [
        {"type": "tool-read_source", "output": {"status": "ok", "usedSourceRef": {
            "kind": "case", "id": "src-22", "title": "固定来源",
            "versionId": "v-source-22", "sourceCaseId": "c-source-22",
            "location": "case:c-source-22@v-source-22",
        }}},
        {"type": "text", "text": f"复述：{LEAK_MARK}"},
    ]
    assert project(parts)[1]["text"] == f"复述：{LEAK_MARK}"
    _revoke_source(database)
    assert project(parts)[1]["text"] == HIDDEN_ANSWER
    assert project(parts)[0]["output"]["status"] == "no_access"
