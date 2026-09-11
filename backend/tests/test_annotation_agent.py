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


def _second_teacher(client: TestClient) -> dict:
    """另建一位普通教师账号：私人讨论隔离与权限用。"""
    from app.modules.auth.passwords import hash_password

    database = client.app.state.database
    database.users.update_one(
        {"id": "u-second-teacher"},
        {"$setOnInsert": {
            "id": "u-second-teacher", "username": "second", "name": "另一位教师",
            "role": "user", "status": "active", "must_change_password": False,
            "campus_verified": True, "token_version": 0,
            "password_hash": hash_password("second-pass"),
        }}, upsert=True,
    )
    return login(client, "second", "second-pass")


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


def test_private_discussion_is_invisible_to_other_teachers(client: TestClient) -> None:
    author = login(client, "user", "user123")
    case = create_case(client, author, "目标正文")
    annotation = create_annotation(client, author, case, "目标正文")
    with agent.override(model=_proposal_model("作者私有修订")):
        assert _send(client, author, case, annotation, "第一轮").status_code == 200
    thread_id = _thread_id(client, case["id"])
    other = _second_teacher(client)
    csrf = _csrf(other)
    listed = client.get(f"/api/cases/{case['id']}/annotations", headers=csrf)
    assert listed.status_code == 403, listed.text
    thread = client.get(f"/api/cases/{case['id']}/agent/thread/{thread_id}", headers=csrf)
    assert thread.status_code in (403, 404), thread.text
    replay = client.post(
        f"/api/cases/{case['id']}/agent/thread/{thread_id}/stream",
        headers=csrf,
        json={"id": "chat-other", "trigger": "submit-message", "messages": [{
            "id": "other", "role": "user",
            "parts": [{"type": "text", "text": "复用作者的批注讨论"}],
        }]},
    )
    assert replay.status_code in (403, 404), replay.text
    again = login(client, "user", "user123")
    row = client.get(
        f"/api/cases/{case['id']}/annotations", headers=_csrf(again),
    ).json()[0]
    assert [revision["replacement"] for revision in row.get("revisions", [])] == ["作者私有修订"]


def test_failed_annotation_run_leaves_no_revision(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")

    async def broken(messages, _info):
        raise RuntimeError("upstream unavailable")

    with agent.override(model=FunctionModel(stream_function=broken)):
        response = _send(client, user, case, annotation, "请修订")
    assert response.status_code == 200, response.text
    row = client.get(
        f"/api/cases/{case['id']}/annotations", headers=_csrf(user),
    ).json()[0]
    assert row.get("revisions", []) == [], row
    snapshot = client.get(f"/api/cases/{case['id']}/agent/thread").json()
    assert snapshot["artifacts"] == [], snapshot
    assert client.get(f"/api/cases/{case['id']}").json()["revision"] == 1
