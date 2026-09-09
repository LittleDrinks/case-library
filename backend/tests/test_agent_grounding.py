"""#215 grounding 回归：生产 Agent 上下文、工具边界和正文选区。"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime as DateTime
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from app.modules.agent import agent


_TAGGED_CASE_TAG_IDS = [
    "tag-seed-1-4", "tag-seed-2-3", "tag-seed-3-1", "tag-seed-4-1",
]
_SOURCE_CASE = {
    "id": "c-grounding-source", "ownerId": "other", "publicationStatus": "public",
    "workflowStatus": "published", "publishedVersionId": "v-grounding-source",
}
_SOURCE_VERSION = {
    "id": "v-grounding-source", "caseId": "c-grounding-source", "number": 1,
    "title": "可读取来源", "document": {"type": "doc", "content": [{
        "type": "paragraph", "content": [{"type": "text", "text": "来源明确写出的内容。"}],
    }]},
}
_SOURCE_LINK = {
    "id": "src-grounding", "caseId": "c-draft-1", "sourceCaseId": "c-grounding-source",
    "versionId": "v-grounding-source", "versionNumber": 1, "title": "可读取来源",
}
_READ_SOURCE_PARTS = [
    {"type": "text", "text": "请读取这个平台来源"},
    {"type": "data-source", "data": {"sourceType": "case", "id": "src-grounding"}},
]
_PLATFORM_PARTS = [{"type": "text", "text": "请检索钱伟长"}]
_SELECTION_DOCUMENT = {"type": "doc", "content": [
    {"type": "paragraph", "content": [{"type": "text", "text": "第一段。"}]},
    {"type": "paragraph", "content": [{"type": "text", "text": "第二段需要修订。"}]},
]}
_SELECTION_PARTS = [
    {"type": "text", "text": "请润色选中的段落"},
    {"type": "data-selection", "data": {"from": 7, "to": 15}},
]


def _auth(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    assert response.status_code == 200
    return response.json()


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _thread_id(client: TestClient, case_id: str) -> str:
    return client.get(f"/api/cases/{case_id}/agent/thread").json()["id"]


def _message_payload(request_id: str, user_message_id: str, parts: list[dict]) -> dict:
    return {
        "id": request_id, "trigger": "submit-message",
        "messages": [{"id": user_message_id, "role": "user", "parts": parts}],
    }


def _answer_model(seen: list[str] | None) -> FunctionModel:
    async def stream(_messages, info):
        if seen is not None:
            seen.append(info.instructions or "")
        yield "已根据当前请求完成回答。"

    return FunctionModel(stream_function=stream)


def _stream_post(
    client: TestClient, auth: dict, case_id: str, request_id: str,
    user_message_id: str, parts: list[dict], model: FunctionModel,
):
    thread_id = _thread_id(client, case_id)
    payload = _message_payload(request_id, user_message_id, parts)
    with agent.override(model=model):
        return client.post(
            f"/api/cases/{case_id}/agent/thread/{thread_id}/stream",
            headers=_csrf(auth), json=payload,
        )


def _post(
    client: TestClient, auth: dict, text: str, parts: list[dict] | None = None,
    seen: list[str] | None = None, case_id: str = "c-draft-1",
):
    message_parts = parts or [{"type": "text", "text": text}]
    return _stream_post(
        client, auth, case_id, "grounding-browser-message", "grounding-user-message",
        message_parts, _answer_model(seen),
    )


def _tool_call(name: str, arguments: dict, call_id: str) -> dict:
    return {0: DeltaToolCall(
        name=name, json_args=json.dumps(arguments), tool_call_id=call_id,
    )}


def _tool_outputs(messages, name: str) -> list:
    return [
        part.content for message in messages for part in getattr(message, "parts", [])
        if getattr(part, "part_kind", "") == "tool-return" and part.tool_name == name
    ]


def _tool_model(
    name: str, arguments: dict, call_id: str, outputs: list, answer: str,
) -> FunctionModel:
    async def stream(messages, _info):
        if not _called(messages, name):
            yield _tool_call(name, arguments, call_id)
            return
        outputs.extend(_tool_outputs(messages, name))
        yield answer

    return FunctionModel(stream_function=stream)


def _assert_context_contains(context: str, expected: tuple[str, ...]) -> None:
    for value in expected:
        assert value in context


def _called(messages, name: str) -> bool:
    return any(
        getattr(part, "part_kind", "") == "tool-call"
        and part.tool_name == name
        for message in messages
        for part in getattr(message, "parts", [])
    )


class _CrossesUtcMidnight(DateTime):
    @classmethod
    def now(cls, tz=None):
        assert tz is not None
        assert getattr(tz, "key", None) == "Asia/Shanghai"
        return DateTime(2026, 9, 8, 16, 30, tzinfo=UTC).astimezone(tz)


def _assert_seed_context(context: str) -> None:
    _assert_context_contains(context, (
        "系统当前日期（北京时间，服务端提供）：2026-09-09",
        "课程：自然辩证法概论", "案例类型：思想实验类", "适用对象：研究生",
        "理论/思政要点：科技自立自强、科学技术创新观、风险评价与决策",
        "课程简称或表述含糊时，不得擅自替换或扩写为其他课程",
        "search_corpus 是平台检索", "status=ok` 只证明本次成功读取",
        "来源没有明确支持的数字、日期、引语和书目", "不能扩展为整篇正文",
    ))


def _create_tagged_case(client: TestClient, auth: dict) -> dict:
    created = client.post(
        "/api/cases", headers=_csrf(auth), json={"title": "标签课程 grounding 案例"}
    )
    assert created.status_code == 200, created.text
    case = created.json()
    saved = client.patch(
        f"/api/cases/{case['id']}", headers=_csrf(auth),
        json={"revision": case["revision"], "tagIds": _TAGGED_CASE_TAG_IDS},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["course"] is None
    return case


def _assert_tag_context(context: str) -> None:
    _assert_context_contains(context, (
        "当前案例 tagIds 按现有标签组解析的名称", "学科：工学",
        "课程：自然辩证法概论", "案例类型：人物传记类", "思政元素：科学家精神",
    ))


def _seed_read_source(database) -> None:
    database.cases.insert_one(deepcopy(_SOURCE_CASE))
    database.case_versions.insert_one(deepcopy(_SOURCE_VERSION))
    database.case_sources.insert_one(deepcopy(_SOURCE_LINK))


def _assert_read_source_output(outputs: list[dict]) -> None:
    assert outputs and outputs[0]["status"] == "ok"
    assert outputs[0]["content"] == "来源明确写出的内容。"
    assert outputs[0]["verification"] == "source_content_read_only"
    assert "verified" not in outputs[0]


def _create_selection_case(client: TestClient, auth: dict) -> dict:
    response = client.post(
        "/api/cases", headers=_csrf(auth),
        json={"title": "选区 grounding 案例", "document": _SELECTION_DOCUMENT},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _selection_model(seen: list[str]) -> FunctionModel:
    async def stream(_messages, info):
        seen.append(info.instructions or "")
        yield "只处理服务端提供的选区。"

    return FunctionModel(stream_function=stream)


def test_production_agent_receives_beijing_date_seed_context_and_grounding(
    client: TestClient,
) -> None:
    auth = _auth(client)
    seen: list[str] = []

    with patch("app.modules.agent.runtime.datetime", _CrossesUtcMidnight):
        response = _post(client, auth, "请结合当前课程回答", seen=seen)

    assert response.status_code == 200, response.text
    _assert_seed_context(seen[0])


def test_new_case_context_resolves_tag_ids_by_existing_groups(client: TestClient) -> None:
    auth = _auth(client)
    case = _create_tagged_case(client, auth)
    seen: list[str] = []
    response = _post(
        client, auth, "请按当前案例课程回答", seen=seen, case_id=case["id"]
    )

    assert response.status_code == 200, response.text
    _assert_tag_context(seen[0])


def test_read_source_result_marks_reading_without_claiming_full_verification(
    client: TestClient,
) -> None:
    _seed_read_source(client.app.state.database)
    auth = _auth(client)
    outputs: list[dict] = []
    response = _stream_post(
        client, auth, "c-draft-1", "grounding-read-message", "grounding-read-user-message",
        _READ_SOURCE_PARTS, _tool_model(
            "read_source", {"source_type": "case", "source_id": "src-grounding"},
            "grounding-read-source", outputs, "已读取本次来源内容；未据此声称全文事实已核实。",
        )
    )
    assert response.status_code == 200, response.text
    _assert_read_source_output(outputs)


def test_platform_search_tool_marks_scope_without_network_claim(client: TestClient) -> None:
    auth = _auth(client)
    outputs: list[dict] = []
    response = _stream_post(
        client, auth, "c-draft-1", "grounding-platform-message",
        "grounding-platform-user-message", _PLATFORM_PARTS, _tool_model(
            "search_corpus", {"query": "钱伟长"}, "grounding-platform-search", outputs,
            "已完成平台检索；这不是联网核验。",
        )
    )
    assert response.status_code == 200, response.text
    assert outputs[0]["scope"] == "platform" and outputs[0]["sources"] == []
    assert outputs[0]["total"] == 0 and "tagCatalog" in outputs[0]


def test_selected_request_keeps_the_server_validated_scope(client: TestClient) -> None:
    auth = _auth(client)
    case = _create_selection_case(client, auth)
    seen: list[str] = []
    response = _stream_post(
        client, auth, case["id"], "grounding-selection-message",
        "grounding-selection-user-message", _SELECTION_PARTS, _selection_model(seen),
    )
    assert response.status_code == 200, response.text
    assert "from=7，to=15，原文：第二段需要修订。" in seen[0]
    assert "局部请求只能处理上述选区，不能扩展为整篇正文" in seen[0]
