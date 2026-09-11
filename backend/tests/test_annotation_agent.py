from __future__ import annotations

import json

import pytest
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from starlette.testclient import TestClient

from app.modules.agent.runtime import agent
from tests.test_annotation_discussion import (
    HEADING,
    create_annotation,
    create_case,
    login,
    paragraph_start,
)


def _proposal_model(replacement: str, reason: str = "补充评价依据", recorder=None) -> FunctionModel:
    async def stream(messages, info):
        if recorder is not None:
            recorder(messages, info)
        async for delta in _proposal_stream(messages, replacement, reason):
            yield delta

    return FunctionModel(stream_function=stream)


async def _proposal_stream(messages, replacement: str, reason: str):
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
                "replacement": replacement, "reason": reason}
        yield {0: DeltaToolCall(name="propose_revision", json_args=json.dumps(args))}
        return
    yield replacement


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
    _run_two_rounds(client, user, case, annotation)
    merged = client.post(
        f"/api/cases/{case['id']}/annotations/{annotation['id']}/merge",
        headers=_csrf(user),
    )
    assert merged.status_code == 200, merged.text
    result = merged.json()
    assert result["annotation"]["status"] == "resolved"
    assert result["annotation"]["revisions"][-1]["status"] == "accepted"
    assert "第二轮改写" in result["case"]["document"]["content"][1]["content"][0]["text"]


def _run_two_rounds(client: TestClient, user: dict, case: dict, annotation: dict) -> None:
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
    _assert_replay_denied(client, case, thread_id, csrf)
    _assert_author_discussion_intact(client, case, annotation)


def _assert_replay_denied(client: TestClient, case: dict, thread_id: str, csrf: dict) -> None:
    replay = client.post(
        f"/api/cases/{case['id']}/agent/thread/{thread_id}/stream",
        headers=csrf,
        json={"id": "chat-other", "trigger": "submit-message", "messages": [{
            "id": "other", "role": "user",
            "parts": [{"type": "text", "text": "复用作者的批注讨论"}],
        }]},
    )
    assert replay.status_code in (403, 404), replay.text


def _private_agent_requests(
    client: TestClient, case: dict, thread_id: str, artifact_id: str, user: dict
):
    root = f"/api/cases/{case['id']}/agent"
    headers = _csrf(user)
    return [
        client.get(f"{root}/thread", headers=headers),
        client.get(f"{root}/threads", headers=headers),
        client.get(f"{root}/threads/{thread_id}", headers=headers),
        client.post(f"{root}/thread/{thread_id}/stream", headers=headers, json={}),
        client.post(f"{root}/thread/{thread_id}/cancel", headers=headers),
        client.get(f"{root}/thread/{thread_id}/events", headers=headers),
        client.post(f"{root}/thread/{thread_id}/artifacts/{artifact_id}/decision",
                    headers=headers, json={"decision": "rejected"}),
        client.post(f"{root}/thread/{thread_id}/writes/missing/undo", headers=headers),
    ]


def _assert_private_agent_denied(
    client: TestClient, case: dict, thread_id: str, artifact_id: str, user: dict
) -> None:
    responses = _private_agent_requests(client, case, thread_id, artifact_id, user)
    assert all(response.status_code in (403, 404) for response in responses)
    assert all("作者私有修订" not in response.text for response in responses)


def _assert_author_private_run_intact(
    client: TestClient, case: dict, snapshot: dict, thread_id: str, artifact_id: str
) -> None:
    author = login(client, "user", "user123")
    after = client.get(f"/api/cases/{case['id']}/agent/thread").json()
    assert after["id"] == thread_id
    assert [run["id"] for run in after["runs"]] == [run["id"] for run in snapshot["runs"]]
    assert [artifact["id"] for artifact in after["artifacts"]] == [artifact_id]
    assert after["artifacts"][0]["status"] == snapshot["artifacts"][0]["status"]
    rows = client.get(f"/api/cases/{case['id']}/annotations", headers=_csrf(author)).json()
    assert rows[0]["revisions"]


def test_private_annotation_run_entries_are_isolated(client: TestClient) -> None:
    author = login(client, "user", "user123")
    case = create_case(client, author, "目标正文")
    annotation = create_annotation(client, author, case, "目标正文")
    with agent.override(model=_proposal_model("作者私有修订")):
        assert _send(client, author, case, annotation, "第一轮").status_code == 200
    _wait_terminal(client, case["id"])
    snapshot = client.get(f"/api/cases/{case['id']}/agent/thread").json()
    thread_id = snapshot["id"]
    artifact_id = snapshot["artifacts"][0]["id"]
    _second_teacher(client)
    _assert_private_agent_denied(
        client, case, thread_id, artifact_id, login(client, "admin", "admin123")
    )
    _assert_private_agent_denied(
        client, case, thread_id, artifact_id, login(client, "second", "second-pass")
    )
    _assert_author_private_run_intact(client, case, snapshot, thread_id, artifact_id)


def _assert_author_discussion_intact(client: TestClient, case: dict, annotation: dict) -> None:
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
        yield  # unreachable: 使函数成为 async generator，抛错发生在首次迭代
    with agent.override(model=FunctionModel(stream_function=broken)):
        response = _send(client, user, case, annotation, "请修订")
    assert response.status_code == 200, response.text
    _wait_terminal(client, case["id"])
    row = client.get(
        f"/api/cases/{case['id']}/annotations", headers=_csrf(user),
    ).json()[0]
    assert row.get("revisions", []) == [], row
    snapshot = client.get(f"/api/cases/{case['id']}/agent/thread").json()
    assert snapshot["artifacts"] == [], snapshot
    assert client.get(f"/api/cases/{case['id']}").json()["revision"] == 1


def _wait_terminal(client: TestClient, case_id: str) -> None:
    """等后台 Run 到达终态，避免后台协程与断言/客户端关闭竞争。"""
    import time

    terminal = {"completed", "failed", "cancelled"}
    for _ in range(100):
        runs = client.get(f"/api/cases/{case_id}/agent/thread").json().get("runs", [])
        if runs and runs[-1].get("status") in terminal:
            return
        time.sleep(0.05)
    raise AssertionError("后台 Run 未在限定时间内到达终态")


def test_wait_terminal_timeout_is_explicit(monkeypatch) -> None:
    from unittest.mock import Mock

    client = Mock()
    client.get.return_value.json.return_value = {"runs": [{"status": "active"}]}
    monkeypatch.setattr("time.sleep", lambda _delay: None)
    with pytest.raises(AssertionError, match="未在限定时间内"):
        _wait_terminal(client, "case-timeout")


def test_admin_cannot_read_or_reply_private_discussion(client: TestClient) -> None:
    author = login(client, "user", "user123")
    case = create_case(client, author, "目标正文")
    annotation = create_annotation(client, author, case, "目标正文")
    admin = login(client, "admin", "admin123")
    csrf = _csrf(admin)
    listed = client.get(f"/api/cases/{case['id']}/annotations", headers=csrf)
    assert listed.status_code == 200
    assert listed.json() == [], {"annotations": listed.json()}
    replied = client.post(
        f"/api/cases/{case['id']}/annotations/{annotation['id']}/replies",
        headers=csrf, json={"content": "审核者插入私人讨论"},
    )
    assert replied.status_code == 403, replied.text
    author = login(client, "user", "user123")
    _assert_author_reply_works(client, case, annotation, author)


def _assert_author_reply_works(client: TestClient, case: dict, annotation: dict, author: dict) -> None:
    own = client.get(
        f"/api/cases/{case['id']}/annotations", headers=_csrf(author),
    ).json()[0]
    assert own.get("replies") in (None, []), own
    answered = client.post(
        f"/api/cases/{case['id']}/annotations/{annotation['id']}/replies",
        headers=_csrf(author), json={"content": "作者补充说明"},
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["replies"][-1]["content"] == "作者补充说明"


def test_admin_still_reads_and_replies_review_annotations(client: TestClient) -> None:
    author = login(client, "user", "user123")
    case = create_case(client, author, "目标正文")
    submission = _submit_case(client, author, case)
    review_annotation = _admin_review_annotation(client, case, submission)
    admin = login(client, "admin", "admin123")
    listed = client.get(
        f"/api/cases/{case['id']}/annotations", headers=_csrf(admin),
    ).json()
    assert [row["id"] for row in listed] == [review_annotation["id"]]
    replied = client.post(
        f"/api/cases/{case['id']}/annotations/{review_annotation['id']}/replies",
        headers=_csrf(admin), json={"content": "审核员追问"},
    )
    assert replied.status_code == 200, replied.text
    author_rows = client.get(
        f"/api/cases/{case['id']}/annotations", headers=_csrf(author),
    ).json()
    assert [row["id"] for row in author_rows] == [review_annotation["id"]]


def _submit_case(client: TestClient, author: dict, case: dict) -> dict:
    response = client.post(
        f"/api/cases/{case['id']}/lifecycle",
        headers=_csrf(author), json={"command": "submit", "revision": case["revision"]},
    )
    assert response.status_code == 200, response.text
    admin = login(client, "admin", "admin123")
    started = client.post(
        f"/api/cases/{case['id']}/lifecycle",
        headers=_csrf(admin),
        json={"command": "start", "revision": response.json()["case"]["revision"]},
    )
    assert started.status_code == 200, started.text
    return {"versionId": response.json()["version"]["id"]}


def _admin_review_annotation(client: TestClient, case: dict, submission: dict) -> dict:
    admin = login(client, "admin", "admin123")
    response = client.post(
        f"/api/cases/{case['id']}/annotations",
        headers=_csrf(admin),
        json={"quote": "目标正文", "section": HEADING,
              "content": "审核意见", "source": "admin"},
    )
    assert response.status_code == 201, response.text
    annotation = response.json()
    assert annotation["versionId"] == submission["versionId"]
    return annotation


def test_annotation_opinion_enters_run_instructions(client: TestClient) -> None:
    author = login(client, "user", "user123")
    case = create_case(client, author, "目标正文")
    annotation = create_annotation(client, author, case, "目标正文")
    captured = {}

    def recorder(messages, info):
        captured["instructions"] = getattr(info, "instructions", "") or ""

    with agent.override(model=_proposal_model("意见驱动修订", recorder=recorder)):
        response = _send(client, author, case, annotation, "请按批注意见修订")
    assert response.status_code == 200, response.text
    instructions = captured["instructions"]
    assert "作者私人意见" in instructions or "请补充评价依据" in instructions, instructions
    assert annotation["quote"] in instructions, instructions


def test_blank_revision_reason_is_rejected_before_artifact(client: TestClient) -> None:
    from app.modules.agent.skills import require_revision_reason
    from pydantic_ai.exceptions import ModelRetry

    try:
        require_revision_reason("   ")
    except ModelRetry as retry:
        assert "理由" in str(retry)
    else:
        raise AssertionError("blank reason must raise ModelRetry")
    assert require_revision_reason(" 具体理由 ") == " 具体理由 "
