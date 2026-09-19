"""批注锚点与AI修订场景步骤。"""
from __future__ import annotations

import json

from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from pytest_bdd import given, parsers, then, when

from app.modules.agent import prosemirror
from app.modules.agent.runtime import agent
from tests.bdd.steps.common_steps import (
    anchor_payload,
    client_of,
    create_annotation,
    create_case,
    csrf_headers,
    get_case,
    paragraph_offset,
    standard_document,
    utf16_size,
)


def _proposal_model(annotation: dict, replacement: str) -> FunctionModel:
    """确定性假模型：一轮 propose_revision 工具调用后收尾。

    提议范围必须命中 Run 锁定的教师选区（即批注锚点 from/to）。
    """

    async def stream(messages, _info):
        start = max(
            index for index, message in enumerate(messages)
            if any(p.part_kind == "user-prompt" for p in getattr(message, "parts", []))
        )
        called = {
            part.tool_name
            for message in messages[start:]
            for part in getattr(message, "parts", [])
            if part.part_kind == "tool-call"
        }
        if "propose_revision" not in called:
            args = {"start": annotation["from"], "end": annotation["to"],
                    "replacement": replacement, "reason": "补充评价依据"}
            yield {0: DeltaToolCall(name="propose_revision",
                                    json_args=json.dumps(args))}
            return
        yield replacement

    return FunctionModel(stream_function=stream)


def _annotation_thread_send(ctx, case: dict, annotation: dict, text: str):
    parts = [
        {"type": "text", "text": text},
        {"type": "data-selection",
         "data": {"from": annotation["from"], "to": annotation["to"]}},
        {"type": "data-annotation", "data": {"id": annotation["id"]}},
    ]
    thread_id = client_of(ctx).get(
        f"/api/cases/{case['id']}/agent/thread"
    ).json()["id"]
    return client_of(ctx).post(
        f"/api/cases/{case['id']}/agent/thread/{thread_id}/stream",
        headers=csrf_headers(ctx, "教师"),
        json={"id": f"message-{text}", "trigger": "submit-message",
              "messages": [{"id": f"user-{text}", "role": "user", "parts": parts}]},
    )


def _annotation_row(ctx, case_id: str) -> dict:
    rows = client_of(ctx).get(
        f"/api/cases/{case_id}/annotations", headers=csrf_headers(ctx, "教师")
    ).json()
    assert rows
    return rows[0]


@given(parsers.parse('教师对"{title}"的"{quote}"挂了批注'))
def annotation_exists(ctx, title, quote):
    create_case(ctx, "教师", title, quote)
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    response = create_annotation(
        ctx, "教师", case["id"], anchor_payload(case, "一、教学说明", quote)
    )
    assert response.status_code == 201, response.text


@given(parsers.parse('教师对"{title}"的"{quote}"挂了批注并已获得AI修订'))
def annotation_with_revision(ctx, title, quote):
    annotation_exists(ctx, title, quote)
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    annotation = _annotation_row(ctx, case["id"])
    with agent.override(model=_proposal_model(annotation, "第一轮AI改写")):
        response = _annotation_thread_send(ctx, case, annotation, "请改写")
    assert response.status_code == 200, response.text


@when(parsers.parse('教师对"{quote}"挂批注"{content}"'))
def teacher_annotates(ctx, quote, content):
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    payload = anchor_payload(case, "一、教学说明", quote, content=content)
    ctx["memo"]["last_response"] = create_annotation(
        ctx, "教师", case["id"], payload
    )


@then(parsers.parse('批注创建成功且引用原文"{quote}"'))
def annotation_created(ctx, quote):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 201, response.text
    assert response.json()["quote"] == quote


@when(parsers.parse('教师在段落开头插入"{inserted}"并保存'))
def insert_at_paragraph_start(ctx, inserted):
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    start = paragraph_offset()
    document = standard_document(f"{inserted}需要打磨的论证")
    steps = [{"stepType": "replace", "from": start, "to": start,
              "slice": {"content": [{"type": "text", "text": inserted}]}}]
    ctx["memo"]["last_response"] = client_of(ctx).patch(
        f"/api/cases/{case['id']}", headers=csrf_headers(ctx, "教师"),
        json={"revision": case["revision"], "title": case["title"],
              "document": document, "steps": steps},
    )
    assert ctx["memo"]["last_response"].status_code == 200, \
        ctx["memo"]["last_response"].text


@then(parsers.parse('批注锚点仍在"{quote}"原文上'))
def anchor_follows_mapping(ctx, quote):
    case_id = ctx["memo"]["current_case_id"]
    row = _annotation_row(ctx, case_id)
    assert row["anchorState"] == "active", row
    case = get_case(ctx, case_id)
    assert prosemirror.text_between(
        case["document"], row["from"], row["to"]
    ) == quote


@when(parsers.parse('教师把该段改写为"{text}"并保存'))
def rewrite_paragraph(ctx, text):
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    start = paragraph_offset()
    end = start + utf16_size("需要打磨的论证")
    document = standard_document(text)
    steps = [{"stepType": "replace", "from": start, "to": end,
              "slice": {"content": [{"type": "text", "text": text}]}}]
    ctx["memo"]["last_response"] = client_of(ctx).patch(
        f"/api/cases/{case['id']}", headers=csrf_headers(ctx, "教师"),
        json={"revision": case["revision"], "title": case["title"],
              "document": document, "steps": steps},
    )
    assert ctx["memo"]["last_response"].status_code == 200, \
        ctx["memo"]["last_response"].text


@then(parsers.parse('批注讨论保留且锚点状态为"{state}"'))
def discussion_kept_anchor_changed(ctx, state):
    case_id = ctx["memo"]["current_case_id"]
    row = _annotation_row(ctx, case_id)
    assert row["anchorState"] == state, row
    assert row["quote"] == "需要打磨的论证"
    assert row["content"]


@when(parsers.parse('AI针对该批注提出修订"{replacement}"'))
def ai_proposes_revision(ctx, replacement):
    import time

    case = get_case(ctx, ctx["memo"]["current_case_id"])
    annotation = _annotation_row(ctx, case["id"])
    with agent.override(model=_proposal_model(annotation, replacement)):
        response = _annotation_thread_send(ctx, case, annotation, "请改写")
    assert response.status_code == 200, response.text
    # 流式 Run 异步收尾：等待修订候选持久化为批注 revisions。
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        row = _annotation_row(ctx, case["id"])
        if row.get("revisions"):
            return
        time.sleep(0.05)
    raise AssertionError(f"AI 修订候选未生成: {row}")


@when("教师采用该修订")
def teacher_accepts_revision(ctx):
    case_id = ctx["memo"]["current_case_id"]
    annotation = _annotation_row(ctx, case_id)
    ctx["memo"]["last_response"] = client_of(ctx).post(
        f"/api/cases/{case_id}/annotations/{annotation['id']}/merge",
        headers=csrf_headers(ctx, "教师"),
    )
    assert ctx["memo"]["last_response"].status_code == 200, \
        ctx["memo"]["last_response"].text


@then(parsers.parse('当前工作稿正文包含"{text}"'))
def document_contains(ctx, text):
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    assert text in document_paragraph_text(case["document"])


def document_paragraph_text(document: dict) -> str:
    return "\n".join(
        "".join(c.get("text", "") for c in block.get("content") or [])
        for block in document.get("content", [])
        if block.get("type") == "paragraph"
    )


@then("批注状态为已解决")
def annotation_resolved(ctx):
    case_id = ctx["memo"]["current_case_id"]
    row = _annotation_row(ctx, case_id)
    assert row["status"] == "resolved", row


@then(parsers.parse('批注的修订状态为"{status}"'))
def revision_status(ctx, status):
    case_id = ctx["memo"]["current_case_id"]
    row = _annotation_row(ctx, case_id)
    assert row["revisions"], row
    assert all(revision["status"] == status for revision in row["revisions"]), row
