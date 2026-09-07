"""#214 初稿写入：空/模板草稿整体生成、明确指令直接写入可撤销、候选确认。

覆盖：直接写入的服务端守卫（作者、工作版本、基线修订号、整篇仅空/模板、
选区仅锁定范围、一次运行一次写入）、撤销的修订号守卫与幂等、整篇候选的
提议-确认流程、工具只真实成功才宣称写入，以及只读运行不暴露写工具。
"""

from __future__ import annotations

import json
import time
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from app.modules.agent import artifacts, prosemirror, writes
from app.modules.agent.models import ArtifactTarget
from app.modules.agent.repository import AgentRepository
from app.modules.agent.visibility import HIDDEN_REVISION
from app.modules.agent.skills import (
    domain_capability,
    propose_document,
    reader_capability,
    write_document,
)
from app.modules.cases.service import CaseError

PARAGRAPHS = ("第一段保持不变。", "第二段需要修订。")
DRAFT_BLOCKS = [
    {"type": "heading", "level": 1, "text": "案例初稿"},
    {"type": "paragraph", "text": "**标记**保留为字面文本"},
    {"type": "bullet_list", "items": ["要点一", "要点二"]},
]
SECOND = ArtifactTarget(from_pos=11, to_pos=19, quote=PARAGRAPHS[1])


def _login(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    assert response.status_code == 200
    return response.json()


def _admin(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200
    return response.json()


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _document(*paragraphs: str) -> dict:
    return {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": text}]}
        for text in paragraphs
    ]}


def _create_case(client: TestClient, auth: dict, document: dict | None = None) -> dict:
    body: dict = {"title": "初稿写入案例"}
    if document is not None:
        body["document"] = document
    response = client.post("/api/cases", headers=_csrf(auth), json=body)
    assert response.status_code == 200
    return response.json()


def _locked_run(database, auth: dict, case: dict,
                target: ArtifactTarget | None = None,
                write_authorized: bool = True):
    repository = AgentRepository(database)
    thread = repository.default_thread(case["id"], auth["user"]["id"])
    run = repository.start_run(
        thread, auth["user"]["id"], [{"type": "text", "text": "写入"}], {},
        f"assistant-{uuid.uuid4().hex}", base_revision=case["revision"],
        target=target, write_authorized=write_authorized,
    )
    return thread, run


def _block_texts(document: dict) -> list[str]:
    return [node["content"][0]["text"] for node in document["content"]]


# ---- 直接写入授权：来自服务端冻结的教师消息判定，而非工具参数 ----


def test_direct_write_authorization_detected_from_message_text() -> None:
    assert writes.direct_write_requested("请把初稿直接写入正文") is True
    assert writes.direct_write_requested("这段直接修改一下") is True
    assert writes.direct_write_requested("帮我生成一份初稿") is False
    assert writes.direct_write_requested("润色一下这个段落") is False
    assert writes.direct_write_requested("不要直接写入，先给我候选") is False
    assert writes.direct_write_requested("") is False


def test_unauthorized_run_cannot_direct_write(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, _document())
    database = client.app.state.database
    _thread, run = _locked_run(database, auth, case, write_authorized=False)
    assert database.agent_runs.find_one({"id": run.id})["writeAuthorized"] is False
    with pytest.raises(CaseError) as excinfo:
        writes.apply_write(
            database, case["id"], run.id, "document", DRAFT_BLOCKS, auth["user"],
        )
    assert excinfo.value.status_code == 403
    assert database.cases.find_one({"id": case["id"]})["revision"] == 1
    assert database.agent_writes.count_documents({}) == 0


def test_write_document_tool_refuses_unauthorized_run(client: TestClient) -> None:
    import asyncio

    auth = _login(client)
    case = _create_case(client, auth, _document())
    database = client.app.state.database
    _thread, run = _locked_run(database, auth, case, write_authorized=False)
    deps = _deps(database, case, run, auth["user"])
    with pytest.raises(ModelRetry) as excinfo:
        asyncio.run(_call(deps, "document", DRAFT_BLOCKS, "初稿"))
    assert "没有明确的直接写入指令" in str(excinfo.value)
    assert deps.wrote is False
    assert database.agent_writes.count_documents({}) == 0


def test_write_refused_when_run_belongs_to_other_case(client: TestClient) -> None:
    auth = _login(client)
    case_a = _create_case(client, auth, _document())
    case_b = _create_case(client, auth, _document())
    database = client.app.state.database
    _thread, run = _locked_run(database, auth, case_a)
    with pytest.raises(CaseError) as excinfo:
        writes.apply_write(
            database, case_b["id"], run.id, "document", DRAFT_BLOCKS, auth["user"],
        )
    assert excinfo.value.status_code == 404
    assert database.cases.find_one({"id": case_b["id"]})["revision"] == 1
    assert database.agent_writes.count_documents({}) == 0
    # 跨案例拒绝后，原运行对自己案例仍可正常写入。
    record = writes.apply_write(
        database, case_a["id"], run.id, "document", DRAFT_BLOCKS, auth["user"],
    )
    assert record["resultRevision"] == 2


# ---- 直接写入：整篇仅空草稿或模板 ----


def test_direct_write_replaces_blank_document(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, _document())
    database = client.app.state.database
    thread, run = _locked_run(database, auth, case)
    record = writes.apply_write(
        database, case["id"], run.id, "document", DRAFT_BLOCKS, auth["user"],
    )
    updated = database.cases.find_one({"id": case["id"]})
    assert updated["revision"] == 2
    assert [node["type"] for node in updated["document"]["content"]] == [
        "heading", "paragraph", "bulletList",
    ]
    row = database.agent_writes.find_one({"runId": run.id}, {"_id": 0})
    assert row["status"] == "written"
    assert row["resultRevision"] == 2
    assert row["beforeDocument"] == {"type": "doc", "content": []}
    types = [event["type"] for event in
             database.agent_thread_events.find({"threadId": thread.id})]
    assert "document.written" in types
    assert any(snapshot["kind"] == "pre_agent_write"
               for snapshot in database.case_snapshots.find({"caseId": case["id"]}))


def test_direct_write_accepts_untouched_template(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    database = client.app.state.database
    _thread, run = _locked_run(database, auth, case)
    record = writes.apply_write(
        database, case["id"], run.id, "document",
        [{"type": "paragraph", "text": "整体生成的初稿。"}], auth["user"],
    )
    assert record["resultRevision"] == 2


def test_direct_write_refuses_full_overwrite_of_existing_body(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, _document(*PARAGRAPHS))
    database = client.app.state.database
    _thread, run = _locked_run(database, auth, case)
    with pytest.raises(CaseError) as excinfo:
        writes.apply_write(
            database, case["id"], run.id, "document", DRAFT_BLOCKS, auth["user"],
        )
    assert excinfo.value.status_code == 422
    assert database.cases.find_one({"id": case["id"]})["revision"] == 1
    assert database.agent_writes.count_documents({}) == 0


# ---- 直接写入：选区仅锁定范围 ----


def test_direct_selection_write_replaces_locked_range(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, _document(*PARAGRAPHS))
    database = client.app.state.database
    _thread, run = _locked_run(database, auth, case, SECOND)
    writes.apply_write(
        database, case["id"], run.id, "selection",
        [{"type": "paragraph", "text": "第一行"}, {"type": "paragraph", "text": "第二行"}],
        auth["user"],
    )
    updated = database.cases.find_one({"id": case["id"]})
    assert updated["revision"] == 2
    paragraphs = prosemirror.paragraphs(updated["document"])
    assert paragraphs[1]["quote"] == "第一行\n第二行"
    assert paragraphs[0]["quote"] == PARAGRAPHS[0]


def test_direct_selection_write_requires_locked_target(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, _document(*PARAGRAPHS))
    database = client.app.state.database
    _thread, run = _locked_run(database, auth, case, target=None)
    with pytest.raises(CaseError) as excinfo:
        writes.apply_write(
            database, case["id"], run.id, "selection", DRAFT_BLOCKS, auth["user"],
        )
    assert excinfo.value.status_code == 422


def test_direct_write_refuses_stale_baseline(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, _document())
    database = client.app.state.database
    _thread, run = _locked_run(database, auth, case)
    database.cases.update_one({"id": case["id"]}, {"$set": {"revision": 2}})
    with pytest.raises(CaseError) as excinfo:
        writes.apply_write(
            database, case["id"], run.id, "document", DRAFT_BLOCKS, auth["user"],
        )
    assert excinfo.value.status_code == 409


def test_only_one_direct_write_per_run(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, _document())
    database = client.app.state.database
    _thread, run = _locked_run(database, auth, case)
    writes.apply_write(
        database, case["id"], run.id, "document", DRAFT_BLOCKS, auth["user"],
    )
    with pytest.raises(CaseError) as excinfo:
        writes.apply_write(
            database, case["id"], run.id, "document",
            [{"type": "paragraph", "text": "再次写入"}], auth["user"],
        )
    assert excinfo.value.status_code == 409
    assert database.agent_writes.count_documents({"runId": run.id}) == 1


def test_invalid_blocks_are_refused(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, _document())
    database = client.app.state.database
    _thread, run = _locked_run(database, auth, case)
    for bad in ([], [{"type": "paragraph", "text": "  "}],
                [{"type": "markdown", "text": "# 标题"}]):
        with pytest.raises(CaseError) as excinfo:
            writes.apply_write(
                database, case["id"], run.id, "document", bad, auth["user"],
            )
        assert excinfo.value.status_code == 422
    assert database.agent_writes.count_documents({}) == 0


# ---- 撤销：修订号守卫、幂等与权限 ----


def _written_case(client: TestClient, auth: dict):
    case = _create_case(client, auth, _document())
    database = client.app.state.database
    thread, run = _locked_run(database, auth, case)
    record = writes.apply_write(
        database, case["id"], run.id, "document", DRAFT_BLOCKS, auth["user"],
    )
    return database, thread, case, record


def test_undo_restores_previous_document_exactly_once(client: TestClient) -> None:
    auth = _login(client)
    database, thread, case, record = _written_case(client, auth)
    result = writes.undo_write(
        database, case["id"], thread.id, record["id"], auth["user"],
    )
    assert result["write"]["status"] == "undone"
    updated = database.cases.find_one({"id": case["id"]})
    assert updated["revision"] == 3
    assert updated["document"] == {"type": "doc", "content": []}
    replay = writes.undo_write(
        database, case["id"], thread.id, record["id"], auth["user"],
    )
    assert replay["write"]["status"] == "undone"
    assert database.cases.find_one({"id": case["id"]})["revision"] == 3


def test_undo_refused_after_body_changed(client: TestClient) -> None:
    auth = _login(client)
    database, thread, case, record = _written_case(client, auth)
    database.cases.update_one({"id": case["id"]}, {"$set": {"revision": 99}})
    with pytest.raises(CaseError) as excinfo:
        writes.undo_write(
            database, case["id"], thread.id, record["id"], auth["user"],
        )
    assert excinfo.value.status_code == 409
    assert database.agent_writes.find_one({"id": record["id"]})["status"] == "written"


def test_undo_requires_author_and_editable_case(client: TestClient) -> None:
    auth = _login(client)
    database, thread, case, record = _written_case(client, auth)
    database.cases.update_one(
        {"id": case["id"]}, {"$set": {"workflowStatus": "submitted"}}
    )
    with pytest.raises(CaseError) as excinfo:
        writes.undo_write(
            database, case["id"], thread.id, record["id"], auth["user"],
        )
    assert excinfo.value.status_code == 409
    intruder = {"id": "u-other", "role": "user"}
    with pytest.raises(CaseError) as denied:
        writes.undo_write(
            database, case["id"], thread.id, record["id"], intruder,
        )
    assert denied.value.status_code == 404


# ---- 整篇候选：确认后才写入 ----


def _pending_document_artifact(client: TestClient, auth: dict, document: dict | None):
    case = _create_case(client, auth, document if document is not None else _document())
    database = client.app.state.database
    thread, run = _locked_run(database, auth, case)
    return database, thread, case, run, artifacts.propose_document_artifact(
        database, case["id"], thread.id, run.id, DRAFT_BLOCKS, "依据资料初稿",
        [], auth["user"],
    )


def _publish(database, repository, run, artifact) -> None:
    from datetime import UTC, datetime

    from app.modules.agent.models import AgentMessage

    message = AgentMessage(
        id=f"assistant-{run.id}", thread_id=run.thread_id, run_id=run.id,
        role="assistant", parts=[{"type": "text", "text": "完成"}],
        created_at=datetime.now(UTC),
    )
    assert repository.complete_run(run.id, message, resources=[], artifact=artifact)


def test_document_candidate_applies_after_accept(client: TestClient) -> None:
    auth = _login(client)
    database, thread, case, run, artifact = _pending_document_artifact(
        client, auth, _document()
    )
    assert artifact.kind == "document"
    assert database.agent_artifacts.count_documents({}) == 0
    _publish(database, AgentRepository(database), run, artifact)
    pending = database.agent_artifacts.find_one({"id": artifact.id}, {"_id": 0})
    assert pending["status"] == "pending"
    assert pending["kind"] == "document"
    result = artifacts.decide_artifact(
        database, case["id"], thread.id, artifact.id, auth["user"], "accepted",
    )
    assert result["artifact"].status == "accepted"
    updated = database.cases.find_one({"id": case["id"]})
    assert updated["revision"] == 2
    assert [node["type"] for node in updated["document"]["content"]] == [
        "heading", "paragraph", "bulletList",
    ]


def test_document_candidate_reject_keeps_body(client: TestClient) -> None:
    auth = _login(client)
    database, thread, case, run, artifact = _pending_document_artifact(
        client, auth, _document()
    )
    _publish(database, AgentRepository(database), run, artifact)
    result = artifacts.decide_artifact(
        database, case["id"], thread.id, artifact.id, auth["user"], "rejected",
    )
    assert result["artifact"].status == "rejected"
    assert database.cases.find_one({"id": case["id"]})["revision"] == 1


def test_document_candidate_refused_on_existing_body(client: TestClient) -> None:
    auth = _login(client)
    with pytest.raises(CaseError) as excinfo:
        _pending_document_artifact(client, auth, _document(*PARAGRAPHS))
    assert excinfo.value.status_code == 422
    assert client.app.state.database.agent_artifacts.count_documents({}) == 0


def test_only_one_artifact_per_run_covers_both_kinds(client: TestClient) -> None:
    auth = _login(client)
    database, thread, case, run, artifact = _pending_document_artifact(
        client, auth, _document()
    )
    _publish(database, AgentRepository(database), run, artifact)
    with pytest.raises(CaseError) as excinfo:
        artifacts.propose_document_artifact(
            database, case["id"], thread.id, run.id,
            [{"type": "paragraph", "text": "换一版"}], "重提", [], auth["user"],
        )
    assert excinfo.value.status_code == 409
    assert database.agent_artifacts.count_documents({"runId": run.id}) == 1


# ---- 工具层：真实成功才宣称写入 ----


def _deps(database, case: dict, run, user: dict, wrote: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        database=database, case_id=case["id"], thread_id=run.thread_id,
        run_id=run.id, user=user, proposed=None, wrote=wrote, evidence=[],
    )


def _ctx(deps) -> SimpleNamespace:
    return SimpleNamespace(deps=deps)


def test_write_document_tool_reports_only_real_success(client: TestClient) -> None:
    import asyncio

    auth = _login(client)
    case = _create_case(client, auth, _document())
    database = client.app.state.database
    _thread, run = _locked_run(database, auth, case)
    deps = _deps(database, case, run, auth["user"])
    output = asyncio.run(_call(deps, "document", DRAFT_BLOCKS, "初稿"))
    assert output["status"] == "written"
    assert output["undoable"] is True
    assert deps.wrote is True
    with pytest.raises(ModelRetry):
        asyncio.run(_call(deps, "document", DRAFT_BLOCKS, "重复写入"))


async def _call(deps, scope, blocks, summary):
    return await write_document(_ctx(deps), scope, blocks, summary)


def test_write_document_tool_retries_on_guard_failure(client: TestClient) -> None:
    import asyncio

    auth = _login(client)
    case = _create_case(client, auth, _document(*PARAGRAPHS))
    database = client.app.state.database
    _thread, run = _locked_run(database, auth, case)
    deps = _deps(database, case, run, auth["user"])
    with pytest.raises(ModelRetry) as excinfo:
        asyncio.run(_call(deps, "document", DRAFT_BLOCKS, "初稿"))
    assert "不能整篇覆盖" in str(excinfo.value)
    assert deps.wrote is False
    assert database.agent_writes.count_documents({}) == 0


def test_propose_document_tool_stages_pending_candidate(client: TestClient) -> None:
    import asyncio

    auth = _login(client)
    case = _create_case(client, auth, _document())
    database = client.app.state.database
    _thread, run = _locked_run(database, auth, case)
    deps = _deps(database, case, run, auth["user"])
    output = asyncio.run(propose_document(_ctx(deps), DRAFT_BLOCKS, "依据资料初稿"))
    assert output["kind"] == "document"
    assert deps.proposed is not None
    with pytest.raises(ModelRetry):
        asyncio.run(propose_document(_ctx(deps), DRAFT_BLOCKS, "再次提议"))
    assert database.agent_artifacts.count_documents({}) == 0


def test_write_tools_only_available_to_author_runs() -> None:
    domain_tools = {tool.__name__ for tool in domain_capability().tools}
    reader_tools = {tool.__name__ for tool in reader_capability().tools}
    assert {"write_document", "propose_document", "propose_revision"} <= domain_tools
    assert domain_tools & reader_tools == {"search_corpus", "read_source"}


# ---- 来源收紧时整篇写入/提议内容随消息一并遮蔽 ----


def test_visibility_masks_document_write_parts_and_blocks() -> None:
    from app.modules.agent.visibility import visible_parts

    def gate(ref_ok: bool):
        return SimpleNamespace(readable=lambda _ref: ref_ok)

    restricted = {"kind": "attachment", "id": "a-1", "title": "资料"}
    parts = [
        {"type": "tool-read_source", "state": "output-available",
         "output": {"status": "ok", "usedSourceRef": restricted}},
        {"type": "tool-write_document", "state": "output-available",
         "input": {"scope": "document", "summary": "初稿摘要",
                   "blocks": [{"type": "paragraph", "text": "初稿正文"}]},
         "output": {"status": "written", "writeId": "w-1"}},
        {"type": "tool-propose_document", "state": "output-available",
         "input": {"blocks": [{"type": "paragraph", "text": "候选正文"}],
                   "reason": "理由"},
         "output": {"artifactId": "a-1", "kind": "document"}},
    ]
    masked = visible_parts(gate(False), parts)
    assert masked[0]["output"]["status"] == "no_access"
    assert masked[1]["input"]["blocks"] == [{"type": "paragraph",
                                             "text": HIDDEN_REVISION}]
    assert masked[1]["input"]["summary"] == HIDDEN_REVISION
    assert masked[1]["output"]["status"] == "written"
    assert masked[2]["input"]["blocks"] == [{"type": "paragraph",
                                             "text": HIDDEN_REVISION}]
    kept = visible_parts(gate(True), parts)
    assert kept == parts


# ---- 端到端：流式运行内直接写入 + 撤销接口 ----


def _submit(client: TestClient, auth: dict, case_id: str, model: FunctionModel,
            text: str = "直接写入初稿"):
    return _submit_with_text(client, auth, case_id, text, model)


def _submit_with_text(client: TestClient, auth: dict, case_id: str, text: str,
                      model: FunctionModel):
    from app.modules.agent.runtime import agent

    thread_id = client.get(f"/api/cases/{case_id}/agent/thread").json()["id"]
    with agent.override(model=model):
        response = client.post(
            f"/api/cases/{case_id}/agent/thread/{thread_id}/stream",
            headers=_csrf(auth),
            json={"id": f"browser-{uuid.uuid4().hex}", "trigger": "submit-message",
                  "messages": [{"id": f"client-{uuid.uuid4().hex}", "role": "user",
                                "parts": [{"type": "text", "text": text}]}]},
        )
    assert response.status_code == 200, response.text
    return thread_id


def _await_run(database, thread_id: str, status: str, deadline: float = 10) -> dict:
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        run = database.agent_runs.find_one(
            {"threadId": thread_id, "status": status}, {"_id": 0}
        )
        if run:
            return run
        time.sleep(0.02)
    raise AssertionError(f"run not reaching status {status}")


def _write_then_text_model() -> FunctionModel:
    call = ModelResponse(parts=[ToolCallPart(
        tool_name="write_document",
        args={"scope": "document", "blocks": DRAFT_BLOCKS, "summary": "按资料生成初稿"},
    )])
    issued: list[bool] = []

    async def stream(_messages, _info):
        if not issued:
            issued.append(True)
            yield {0: DeltaToolCall(
                name="write_document",
                json_args=json.dumps(call.parts[0].args_as_dict()),
                tool_call_id="delta-write",
            )}
        else:
            yield "已直接写入正文，可撤销。"

    return FunctionModel(stream_function=stream)


def test_streamed_direct_write_lands_and_undo_api_restores(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, _document())
    database = client.app.state.database
    thread_id = _submit(client, auth, case["id"], _write_then_text_model())
    _await_run(database, thread_id, "completed")
    updated = database.cases.find_one({"id": case["id"]})
    assert updated["revision"] == 2
    assert [node["type"] for node in updated["document"]["content"]] == [
        "heading", "paragraph", "bulletList",
    ]
    run = database.agent_runs.find_one(
        {"threadId": thread_id}, {"_id": 0, "toolTimings": 1, "writeAuthorized": 1}
    )
    assert run["writeAuthorized"] is True
    write = database.agent_writes.find_one({"threadId": thread_id}, {"_id": 0})
    assert write["status"] == "written"
    response = client.post(
        f"/api/cases/{case['id']}/agent/thread/{thread_id}"
        f"/writes/{write['id']}/undo",
        headers=_csrf(auth),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["write"]["status"] == "undone"
    assert body["case"]["revision"] == 3
    assert body["case"]["document"] == {"type": "doc", "content": []}


def test_normal_generation_message_blocks_mistaken_direct_write(client: TestClient) -> None:
    """普通生成请求即使模型误调用写工具，服务端也不落库。"""
    auth = _login(client)
    case = _create_case(client, auth, _document())
    database = client.app.state.database
    thread_id = _submit_with_text(
        client, auth, case["id"], "帮我生成一份初稿", _write_then_text_model()
    )
    _await_run(database, thread_id, "completed")
    run = database.agent_runs.find_one(
        {"threadId": thread_id}, {"_id": 0, "writeAuthorized": 1}
    )
    assert run["writeAuthorized"] is False
    assert database.cases.find_one({"id": case["id"]})["revision"] == 1
    assert database.cases.find_one({"id": case["id"]})["document"] == {
        "type": "doc", "content": [],
    }
    assert database.agent_writes.count_documents({}) == 0
    # 误调用被服务端拒绝并回灌为工具错误，运行仍正常完成。
    message = database.agent_messages.find_one(
        {"threadId": thread_id, "role": "assistant"}
    )
    assert any(part.get("type") == "tool-write_document"
               and part.get("state") == "output-error"
               for part in message["parts"])


def test_undo_api_rejects_non_author(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, _document())
    database = client.app.state.database
    thread_id = _submit(client, auth, case["id"], _write_then_text_model())
    _await_run(database, thread_id, "completed")
    write = database.agent_writes.find_one({"threadId": thread_id}, {"_id": 0})
    response = client.post(
        f"/api/cases/{case['id']}/agent/thread/{thread_id}"
        f"/writes/{write['id']}/undo",
        headers=_csrf(_admin(client)),
    )
    assert response.status_code == 403
    assert database.cases.find_one({"id": case["id"]})["revision"] == 2
