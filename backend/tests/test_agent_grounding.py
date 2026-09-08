"""#215 grounding 回归：生产 Agent 上下文、工具边界和正文选区。"""

from __future__ import annotations

import json
from datetime import UTC, datetime as DateTime
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from app.modules.agent import agent


def _auth(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    assert response.status_code == 200
    return response.json()


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _post(
    client: TestClient, auth: dict, text: str, parts: list[dict] | None = None,
    seen: list[str] | None = None, case_id: str = "c-draft-1",
):
    thread_id = client.get(f"/api/cases/{case_id}/agent/thread").json()["id"]

    async def stream(messages, info):
        if seen is not None:
            seen.append(info.instructions or "")
        yield "已根据当前请求完成回答。"

    with agent.override(model=FunctionModel(stream_function=stream)):
        return client.post(
            f"/api/cases/{case_id}/agent/thread/{thread_id}/stream",
            headers=_csrf(auth),
            json={
                "id": "grounding-browser-message",
                "trigger": "submit-message",
                "messages": [{
                    "id": "grounding-user-message",
                    "role": "user",
                    "parts": parts or [{"type": "text", "text": text}],
                }],
            },
        )


def _called(messages, name: str) -> bool:
    return any(
        getattr(part, "part_kind", "") == "tool-call"
        and part.tool_name == name
        for message in messages
        for part in getattr(message, "parts", [])
    )


def test_production_agent_receives_beijing_date_seed_context_and_grounding(
    client: TestClient,
) -> None:
    auth = _auth(client)
    seen: list[str] = []

    class CrossesUtcMidnight(DateTime):
        @classmethod
        def now(cls, tz=None):
            assert tz is not None
            assert getattr(tz, "key", None) == "Asia/Shanghai"
            return DateTime(2026, 9, 8, 16, 30, tzinfo=UTC).astimezone(tz)

    with patch("app.modules.agent.runtime.datetime", CrossesUtcMidnight):
        response = _post(client, auth, "请结合当前课程回答", seen=seen)

    assert response.status_code == 200, response.text
    context = seen[0]
    assert "系统当前日期（北京时间，服务端提供）：2026-09-09" in context
    assert "课程：自然辩证法概论" in context
    assert "案例类型：思想实验类" in context
    assert "适用对象：研究生" in context
    assert "理论/思政要点：科技自立自强、科学技术创新观、风险评价与决策" in context
    assert "课程简称或表述含糊时，不得擅自替换或扩写为其他课程" in context
    assert "search_corpus 是平台检索" in context
    assert "status=ok` 只证明本次成功读取" in context
    assert "来源没有明确支持的数字、日期、引语和书目" in context
    assert "不能扩展为整篇正文" in context


def test_new_case_context_resolves_tag_ids_by_existing_groups(client: TestClient) -> None:
    auth = _auth(client)
    created = client.post(
        "/api/cases",
        headers=_csrf(auth),
        json={"title": "标签课程 grounding 案例"},
    )
    assert created.status_code == 200, created.text
    case = created.json()
    saved = client.patch(
        f"/api/cases/{case['id']}",
        headers=_csrf(auth),
        json={
            "revision": case["revision"],
            "tagIds": ["tag-seed-1-4", "tag-seed-2-3", "tag-seed-3-1", "tag-seed-4-1"],
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["course"] is None
    seen: list[str] = []

    response = _post(
        client, auth, "请按当前案例课程回答", seen=seen, case_id=case["id"]
    )

    assert response.status_code == 200, response.text
    context = seen[0]
    assert "当前案例 tagIds 按现有标签组解析的名称" in context
    assert "学科：工学" in context
    assert "课程：自然辩证法概论" in context
    assert "案例类型：人物传记类" in context
    assert "思政元素：科学家精神" in context


def test_read_source_result_marks_reading_without_claiming_full_verification(
    client: TestClient,
) -> None:
    database = client.app.state.database
    database.cases.insert_one({
        "id": "c-grounding-source", "ownerId": "other", "publicationStatus": "public",
        "workflowStatus": "published", "publishedVersionId": "v-grounding-source",
    })
    database.case_versions.insert_one({
        "id": "v-grounding-source", "caseId": "c-grounding-source", "number": 1,
        "title": "可读取来源", "document": {
            "type": "doc", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "来源明确写出的内容。"},
            ]}],
        },
    })
    database.case_sources.insert_one({
        "id": "src-grounding", "caseId": "c-draft-1",
        "sourceCaseId": "c-grounding-source", "versionId": "v-grounding-source",
        "versionNumber": 1, "title": "可读取来源",
    })
    auth = _auth(client)
    thread_id = client.get("/api/cases/c-draft-1/agent/thread").json()["id"]
    outputs: list[dict] = []

    async def stream(messages, _info):
        if not _called(messages, "read_source"):
            yield {0: DeltaToolCall(
                name="read_source",
                json_args=json.dumps({"source_type": "case", "source_id": "src-grounding"}),
                tool_call_id="grounding-read-source",
            )}
            return
        for message in messages:
            for part in getattr(message, "parts", []):
                if getattr(part, "part_kind", "") == "tool-return":
                    if part.tool_name == "read_source":
                        outputs.append(part.content)
        yield "已读取本次来源内容；未据此声称全文事实已核实。"

    with agent.override(model=FunctionModel(stream_function=stream)):
        response = client.post(
            f"/api/cases/c-draft-1/agent/thread/{thread_id}/stream",
            headers=_csrf(auth),
            json={
                "id": "grounding-read-message",
                "trigger": "submit-message",
                "messages": [{
                    "id": "grounding-read-user-message", "role": "user",
                    "parts": [{"type": "text", "text": "请读取这个平台来源"}, {
                        "type": "data-source",
                        "data": {"sourceType": "case", "id": "src-grounding"},
                    }],
                }],
            },
        )

    assert response.status_code == 200, response.text
    assert outputs and outputs[0]["status"] == "ok"
    assert outputs[0]["content"] == "来源明确写出的内容。"
    assert outputs[0]["verification"] == "source_content_read_only"
    assert "verified" not in outputs[0]


def test_platform_search_tool_marks_scope_without_network_claim(client: TestClient) -> None:
    auth = _auth(client)
    thread_id = client.get("/api/cases/c-draft-1/agent/thread").json()["id"]
    outputs: list[dict] = []

    async def stream(messages, _info):
        if not _called(messages, "search_corpus"):
            yield {0: DeltaToolCall(
                name="search_corpus",
                json_args=json.dumps({"query": "钱伟长"}),
                tool_call_id="grounding-platform-search",
            )}
            return
        for message in messages:
            for part in getattr(message, "parts", []):
                if getattr(part, "part_kind", "") == "tool-return":
                    if part.tool_name == "search_corpus":
                        outputs.append(part.content)
        yield "已完成平台检索；这不是联网核验。"

    with agent.override(model=FunctionModel(stream_function=stream)):
        response = client.post(
            f"/api/cases/c-draft-1/agent/thread/{thread_id}/stream",
            headers=_csrf(auth),
            json={
                "id": "grounding-platform-message",
                "trigger": "submit-message",
                "messages": [{
                    "id": "grounding-platform-user-message", "role": "user",
                    "parts": [{"type": "text", "text": "请检索钱伟长"}],
                }],
            },
        )

    assert response.status_code == 200, response.text
    assert outputs == [{"scope": "platform", "sources": []}]


def test_selected_request_keeps_the_server_validated_scope(client: TestClient) -> None:
    auth = _auth(client)
    response = client.post(
        "/api/cases", headers=_csrf(auth), json={
            "title": "选区 grounding 案例",
            "document": {"type": "doc", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "第一段。"}]},
                {"type": "paragraph", "content":[
                    {"type": "text", "text": "第二段需要修订。"},
                ]},
            ]},
        },
    )
    case = response.json()
    thread_id = client.get(f"/api/cases/{case['id']}/agent/thread").json()["id"]
    seen: list[str] = []

    async def stream(_messages, info):
        seen.append(info.instructions or "")
        yield "只处理服务端提供的选区。"

    with agent.override(model=FunctionModel(stream_function=stream)):
        response = client.post(
            f"/api/cases/{case['id']}/agent/thread/{thread_id}/stream",
            headers=_csrf(auth),
            json={
                "id": "grounding-selection-message",
                "trigger": "submit-message",
                "messages": [{
                    "id": "grounding-selection-user-message", "role": "user",
                    "parts": [
                        {"type": "text", "text": "请润色选中的段落"},
                        {"type": "data-selection", "data": {"from": 7, "to": 15}},
                    ],
                }],
            },
        )

    assert response.status_code == 200, response.text
    assert "from=7，to=15，原文：第二段需要修订。" in seen[0]
    assert "局部请求只能处理上述选区，不能扩展为整篇正文" in seen[0]
