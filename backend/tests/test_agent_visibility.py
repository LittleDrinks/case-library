"""Issue22 来源权限投影回归：快照、恢复流与模型历史共用同一可见性收敛。

收紧（来源转私密）后：受影响 assistant 回答、推理、修订提议在快照、
SSE 恢复、下一轮模型历史三个输出面都不得复述来源正文；私人 Thread
与数据库原始历史保持完整。全部走真实 HTTP（TestClient → FastAPI 栈）。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

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
from app.modules.agent.models import SourceRef
from app.modules.agent.deps import ToolDeps
from app.modules.agent.service import _reader_accessible
from app.modules.agent.repository import AgentRepository

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
    user = database.users.find_one({"id": "u-user-demo"})
    result = read_source(database, None, user,
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
    user = database.users.find_one({"id": "u-user-demo"})
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


def test_parts_projector_reads_current_campus_grant_after_revoke(client: TestClient) -> None:
    database = client.app.state.database
    database.materials.insert_one({
        "id": "m-campus-current", "status": "active", "title": "合成校内资料",
        "accessLevel": "campus", "createdBy": "u-other",
    })
    database.users.update_one(
        {"id": "u-user-demo"}, {"$set": {"campus_verified": True}}
    )
    user = database.users.find_one({"id": "u-user-demo"})
    project = parts_projector(database, user, "c-draft-1")
    parts = [
        {"type": "tool-read_source", "output": {"status": "ok", "usedSourceRef": {
            "kind": "material", "id": "m-campus-current", "title": "合成校内资料",
            "location": "material:m-campus-current",
        }}},
        {"type": "text", "text": "合成校内正文"},
    ]

    assert project(parts)[1]["text"] == "合成校内正文"
    database.users.update_one(
        {"id": "u-user-demo"}, {"$set": {"campus_verified": False}}
    )

    revoked = project(parts)
    assert revoked[1]["text"] == HIDDEN_ANSWER
    assert revoked[0]["output"] == {"status": "no_access", "detail": "来源当前不可读"}


def test_metadata_only_search_hit_is_rechecked_against_current_directory_and_session(
    client: TestClient,
) -> None:
    database = client.app.state.database
    database.materials.insert_one({
        "id": "m-metadata-current", "status": "active", "title": "当前公开引用标题",
        "accessLevel": "campus", "publicReferenceCount": 1, "createdBy": "u-other",
    })
    database.users.update_one(
        {"id": "u-user-demo"}, {"$set": {"campus_verified": False}}
    )
    user = database.users.find_one({"id": "u-user-demo"})
    project = parts_projector(database, user, "c-draft-1")
    parts = [
        {"type": "tool-search_corpus", "output": {"sources": [{
            "kind": "material", "id": "m-metadata-current", "title": "当前公开引用标题",
            "snippet": "当前公开引用标题", "contentAvailable": False,
        }]}},
        {"type": "text", "text": "按目录标题完成普通创作：当前公开引用标题"},
    ]

    assert project(parts)[0]["output"]["sources"]
    assert project(parts)[1]["text"].startswith("按目录标题")

    database.materials.update_one(
        {"id": "m-metadata-current"}, {"$set": {"publicReferenceCount": 0}}
    )
    hidden = project(parts)
    assert hidden[0]["output"]["sources"] == []
    assert hidden[1]["text"] == HIDDEN_ANSWER

    database.materials.update_one(
        {"id": "m-metadata-current"},
        {"$set": {"publicReferenceCount": 1, "title": "目录标题已更新"}},
    )
    renamed = project(parts)
    assert renamed[0]["output"]["sources"] == []
    assert renamed[1]["text"] == HIDDEN_ANSWER

    database.materials.update_one(
        {"id": "m-metadata-current"},
        {"$set": {"title": "当前公开引用标题", "status": "withdrawn"}},
    )
    offline = project(parts)
    assert offline[0]["output"]["sources"] == []
    assert offline[1]["text"] == HIDDEN_ANSWER

    database.materials.update_one(
        {"id": "m-metadata-current"},
        {"$set": {
            "status": "active", "publicReferenceCount": 1, "accessLevel": "unknown",
        }},
    )
    invalid_level = project(parts)
    assert invalid_level[0]["output"]["sources"] == []
    assert invalid_level[1]["text"] == HIDDEN_ANSWER

    database.materials.update_one(
        {"id": "m-metadata-current"},
        {"$set": {"accessLevel": "campus"}},
    )
    database.users.update_one({"id": user["id"]}, {"$set": {"status": "disabled"}})
    disabled = project(parts)
    assert disabled[0]["output"]["sources"] == []
    assert disabled[1]["text"] == HIDDEN_ANSWER

    database.users.update_one(
        {"id": user["id"]},
        {"$inc": {"token_version": 1}, "$set": {"status": "active"}},
    )
    expired = project(parts)
    assert expired[0]["output"]["sources"] == []
    assert expired[1]["text"] == HIDDEN_ANSWER


def test_production_run_inherits_history_source_dependencies_until_revocation(
    client: TestClient,
) -> None:
    from io import BytesIO

    database = client.app.state.database
    user_id = "u-user-demo"
    material_id = "m-agent-history-campus"
    blob_id = "b-agent-history-campus"
    database.users.update_one({"id": user_id}, {"$set": {"campus_verified": True}})
    database.materials.insert_one({
        "id": material_id, "status": "active", "title": "合成历史校内资料",
        "accessLevel": "campus", "createdBy": "u-other", "blobId": blob_id,
        "filename": "synthetic.txt", "mediaType": "text/plain", "size": 26,
    })
    database.case_materials.insert_one({
        "id": "cm-agent-history-campus", "caseId": "c-draft-1",
        "materialId": material_id, "title": "合成历史校内资料",
    })
    client.app.state.blob_store.put(
        blob_id, BytesIO(b"Synthetic campus source body."), 29, "text/plain"
    )
    auth = _auth(client)
    thread_id = _thread(client, "c-draft-1")

    async def read_and_answer(messages, _info):
        if "read_source" not in _tool_names(messages):
            yield _tool_delta(
                "read_source", {"source_type": "material", "source_id": material_id},
                "history-campus-read",
            )
            return
        yield "第一轮已读取合成校内正文。"

    first = _post_stream(
        client, auth, "c-draft-1", thread_id, _stream_body("读取校内资料"),
        FunctionModel(stream_function=read_and_answer),
    )
    assert first.status_code == 200, first.text
    stored = database.agent_messages.find_one({"threadId": thread_id, "role": "assistant"})
    body_dependency = stored["metadata"]["_sourceDependencies"][0]
    assert body_dependency["id"] == material_id
    assert "contentAvailable" not in body_dependency

    async def revoke_during_second_turn(messages, _info):
        assert "第一轮已读取合成校内正文" in _history_texts([messages])
        database.users.update_one({"id": user_id}, {"$set": {"campus_verified": False}})
        yield LEAK_MARK

    second = _post_stream(
        client, auth, "c-draft-1", thread_id,
        _stream_body("继续复述上一轮", "second-campus-message"),
        FunctionModel(stream_function=revoke_during_second_turn),
    )
    assert second.status_code == 200, second.text
    assert LEAK_MARK not in second.text
    run = database.agent_runs.find_one(
        {"threadId": thread_id}, sort=[("startedAt", -1)]
    )
    assert run["status"] == "cancelled"
    assert database.agent_messages.count_documents({"runId": run["id"], "role": "assistant"}) == 0
    assert database.agent_artifacts.count_documents({"runId": run["id"]}) == 0
    snapshot = _snapshot(client, thread_id)
    assert HIDDEN_ANSWER in json.dumps(snapshot, ensure_ascii=False)
    assert "_sourceDependencies" not in json.dumps(snapshot, ensure_ascii=False)
    assert LEAK_MARK not in _replay(client, "c-draft-1", thread_id)


def test_active_agent_run_rechecks_campus_sources_before_output(client: TestClient) -> None:
    database = client.app.state.database
    database.materials.insert_one({
        "id": "m-run-campus", "status": "active", "title": "合成校内资料",
        "accessLevel": "campus", "createdBy": "u-other",
    })
    database.users.update_one(
        {"id": "u-user-demo"}, {"$set": {"campus_verified": True}}
    )
    stale_user = database.users.find_one({"id": "u-user-demo"})
    database.users.update_one(
        {"id": "u-user-demo"}, {"$set": {"campus_verified": False}}
    )
    source = SourceRef(kind="material", id="m-run-campus", title="合成校内资料")
    deps = ToolDeps(
        database=database, case_id="c-draft-1", thread_id="t-run", run_id="r-run",
        user=stale_user, catalog=client.app.state.search_catalog,
        catalog_state=client.app.state.catalog_state,
        secret_path=client.app.state.settings.app_secret_file,
        hits=[source],
    )
    context = SimpleNamespace(review=False, case={"versionId": None}, deps=deps)

    assert _reader_accessible(context) is False


def test_review_run_rechecks_campus_sources_after_admin_access_check(
    client: TestClient,
) -> None:
    database = client.app.state.database
    admin = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    ).json()["user"]
    database.users.update_one(
        {"id": admin["id"]}, {"$set": {"campus_verified": True}}
    )
    stale_user = database.users.find_one({"id": admin["id"]})
    database.users.update_one(
        {"id": admin["id"]}, {"$set": {"campus_verified": False}}
    )
    database.cases.insert_one({
        "id": "c-review-campus-access", "workflowStatus": "reviewing",
        "submittedVersionId": "v-review-campus-access",
    })
    database.agent_threads.insert_one({
        "id": "t-review-campus-access", "caseId": "c-review-campus-access",
    })
    database.agent_runs.insert_one({
        "id": "r-review-campus-access", "threadId": "t-review-campus-access",
        "submittedVersionId": "v-review-campus-access",
    })
    database.materials.insert_one({
        "id": "m-review-campus-access", "status": "active",
        "title": "合成校内审核资料", "accessLevel": "campus", "createdBy": "u-other",
    })
    source = SourceRef(
        kind="material", id="m-review-campus-access", title="合成校内审核资料"
    )
    deps = ToolDeps(
        database=database, case_id="c-review-campus-access",
        thread_id="t-review-campus-access", run_id="r-review-campus-access",
        user=stale_user, catalog=client.app.state.search_catalog,
        catalog_state=client.app.state.catalog_state,
        secret_path=client.app.state.settings.app_secret_file, hits=[source],
    )
    context = SimpleNamespace(
        review=True, case={"id": "c-review-campus-access", "versionId": None},
        run=SimpleNamespace(id="r-review-campus-access", user_id=admin["id"]),
        repository=AgentRepository(database), deps=deps,
    )

    assert _reader_accessible(context) is False


@pytest.mark.parametrize("revoke_after_first_batch", [False, True])
def test_active_recovery_does_not_replay_revoked_source_chunks(client: TestClient, revoke_after_first_batch: bool) -> None:
    import asyncio
    from threading import Event
    from test_agent_runs_lifecycle import (
        _asgi_scope, _login_cookie, _post_async, _spawn_disconnected_app, _stop_loop,
    )

    database = client.app.state.database
    _seed_source(database)
    auth = _login_cookie(client)
    thread_id = _thread(client, "c-draft-1")
    reached, release, disconnect = Event(), Event(), Event()

    async def answer(messages, _info):
        if "read_source" not in _tool_names(messages):
            yield _tool_delta("read_source", {"source_type": "case", "source_id": "src-22"}, "active-read")
            return
        for _ in range(225):
            yield LEAK_MARK
        reached.set()
        await asyncio.to_thread(release.wait, 10)
        yield LEAK_MARK + "，结束"

    model = FunctionModel(stream_function=answer)
    pending, _, pool = _post_async(client.app, "读取后刷新", model)
    chunks = []
    try:
        assert reached.wait(5)
        assert _snapshot(client, thread_id)["activeRun"]
        scope = _asgi_scope({"Cookie": auth["cookie"]}, thread_id)
        scope.update(method="GET", path=f"/api/cases/c-draft-1/agent/thread/{thread_id}/events")

        async def receive_chunk(message):
            raw = message.get("body", b"").decode()
            if raw:
                chunks.append(raw)
                if revoke_after_first_batch and len(chunks) == 1:
                    _revoke_source(database)
                release.set()

        _, reading, loop = _spawn_disconnected_app(
            client.app, scope, b"", model, disconnect, receive_chunk, {},
        )
        try:
            reading.result(timeout=10)
            if revoke_after_first_batch:
                assert any(LEAK_MARK in chunk for chunk in chunks[:1])
                result = "".join(chunks[1:])
                assert LEAK_MARK not in result
                assert '"type":"abort"' in result or HIDDEN_ANSWER in result
            else:
                result = "".join(chunks)
                assert LEAK_MARK in result
                assert HIDDEN_ANSWER not in result
        finally:
            disconnect.set()
            _stop_loop(loop, reading)
    finally:
        release.set()
        pending.result(timeout=10)
        pool.shutdown()
