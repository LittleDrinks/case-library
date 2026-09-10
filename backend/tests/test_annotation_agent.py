from __future__ import annotations

import json

from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from starlette.testclient import TestClient

from app.modules.agent.runtime import agent
from tests.test_annotation_discussion import (
    create_annotation,
    create_case,
    login,
    paragraph_start,
)


def _proposal_model(replacement: str) -> FunctionModel:
    async def stream(messages, _info):
        start = max(
            index for index, message in enumerate(messages)
            if any(part.part_kind == "user-prompt" for part in getattr(message, "parts", []))
        )
        called = {
            part.tool_name
            for message in messages[start:]
            for part in getattr(message, "parts", [])
            if part.part_kind == "tool-call"
        }
        if "propose_revision" not in called:
            args = {"start": paragraph_start(), "end": paragraph_start() + 4,
                    "replacement": replacement, "reason": "补充评价依据"}
            yield {0: DeltaToolCall(name="propose_revision", json_args=json.dumps(args))}
            return
        yield replacement

    return FunctionModel(stream_function=stream)


def _csrf(user: dict) -> dict:
    return {"X-CSRF-Token": user["csrfToken"]}


def _thread_id(client: TestClient, case_id: str) -> str:
    return client.get(f"/api/cases/{case_id}/agent/thread").json()["id"]


def _send(client: TestClient, user: dict, case: dict, annotation: dict, text: str):
    parts = [
        {"type": "text", "text": text},
        {"type": "data-selection", "data": {
            "from": annotation["from"], "to": annotation["to"]}},
        {"type": "data-annotation", "data": {"id": annotation["id"]}},
    ]
    thread_id = _thread_id(client, case["id"])
    return client.post(
        f"/api/cases/{case['id']}/agent/thread/{thread_id}/stream",
        headers=_csrf(user),
        json={"id": f"message-{text}", "trigger": "submit-message", "messages": [{
            "id": f"user-{text}", "role": "user", "parts": parts,
        }]},
    )


def test_two_annotation_runs_append_revisions_and_merge_latest(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    with agent.override(model=_proposal_model("第一轮改写")):
        first = _send(client, user, case, annotation, "第一轮")
    assert first.status_code == 200, first.text
    with agent.override(model=_proposal_model("第二轮改写")):
        second = _send(client, user, case, annotation, "第二轮")
    assert second.status_code == 200, second.text
    snapshot = client.get(f"/api/cases/{case['id']}/agent/thread").json()
    assert snapshot["artifacts"], snapshot
    assert snapshot["artifacts"][0]["annotationId"] == annotation["id"]
    assert len(snapshot["artifacts"]) == 2, len(snapshot["artifacts"])
    row = client.get(f"/api/cases/{case['id']}/annotations").json()[0]
    assert [revision["replacement"] for revision in row.get("revisions", [])] == [
        "第一轮改写", "第二轮改写"
    ], {"annotation": row, "runs": snapshot["runs"], "artifacts": snapshot["artifacts"]}
    assert row["revisions"][0]["artifactId"]
    merged = client.post(
        f"/api/cases/{case['id']}/annotations/{annotation['id']}/merge",
        headers=_csrf(user),
    )
    assert merged.status_code == 200, merged.text
    result = merged.json()
    assert result["annotation"]["status"] == "resolved"
    assert result["annotation"]["revisions"][-1]["status"] == "accepted"
    assert "第二轮改写" in result["case"]["document"]["content"][1]["content"][0]["text"]
