"""Issue169 读者私人对话：绑定批准版本、跨账号隔离与只读能力边界。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from app.modules.agent import service
from app.modules.agent.repository import AgentRepository
from app.modules.agent.runtime import agent
from app.modules.agent.skills import reader_capability

CASE = "c-02"
VERSION = "cv-seed-c-02-v1"
THREAD_PATH = f"/api/cases/{CASE}/agent/thread"
THREADS_PATH = f"/api/cases/{CASE}/agent/threads"
READER = {"username": "user", "password": "user123"}
ROSTER = {"username": "10000001", "password": "Demo-10000001-2026!"}


def _login(client: TestClient, account: dict) -> dict:
    response = client.post("/api/auth/login", json=account)
    assert response.status_code == 200
    return response.json()


def _second_reader(client: TestClient) -> dict:
    """名册账号首次改密后成为第二位可用读者。"""
    first = _login(client, ROSTER)
    client.post(
        "/api/auth/change-password",
        headers=_csrf(first),
        json={"currentPassword": ROSTER["password"], "newPassword": "Reader-2026-pass!"},
    )
    return _login(client, {**ROSTER, "password": "Reader-2026-pass!"})


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _default_thread(client: TestClient, auth: dict, version_id: str = VERSION) -> dict:
    response = client.get(THREAD_PATH, params={"versionId": version_id})
    assert response.status_code == 200
    return response.json()


def _message(text: str, message_id: str = "reader-message", skills: list | None = None) -> dict:
    parts: list[dict] = [{"type": "text", "text": text}]
    parts += [{"type": "data-skill", "data": {"skillId": skill}} for skill in (skills or [])]
    return {"id": message_id, "role": "user", "parts": parts}


def _send(
    client: TestClient, auth: dict, thread_id: str, text: str,
    skills: list | None = None, version_id: str | None = None,
):
    path = f"{THREAD_PATH}/{thread_id}/stream"
    if version_id:
        path += f"?versionId={version_id}"
    return client.post(
        path,
        headers=_csrf(auth),
        json={
            "id": "reader-chat", "trigger": "submit-message",
            "messages": [_message(text, skills=skills)],
        },
    )


def test_reader_default_thread_binds_approved_version(client: TestClient) -> None:
    auth = _login(client, READER)

    snapshot = _default_thread(client, auth)

    assert snapshot["caseId"] == CASE and snapshot["versionId"] == VERSION
    assert snapshot["messages"] == []
    assert _default_thread(client, auth)["id"] == snapshot["id"]
    threads = client.get(THREADS_PATH, params={"versionId": VERSION}).json()
    assert [item["id"] for item in threads] == [snapshot["id"]]
    assert threads[0]["versionId"] == VERSION


def test_reader_thread_requires_login(client: TestClient) -> None:
    assert client.get(THREAD_PATH, params={"versionId": VERSION}).status_code == 401
    assert client.get(THREADS_PATH, params={"versionId": VERSION}).status_code == 401


def test_reader_thread_rejects_unreadable_versions(client: TestClient) -> None:
    auth = _login(client, READER)

    for case_id, version_id in (
        (CASE, "cv-missing"), (CASE, "cv-seed-c-05-v1"),
        ("c-pending-1", "cv-seed-c-pending-1-v1"),
    ):
        path = f"/api/cases/{case_id}/agent/thread"
        response = client.get(path, params={"versionId": version_id})
        assert response.status_code == 404, version_id
        assert response.json() == {"detail": "案例版本不存在"}
    created = client.post(
        THREADS_PATH, headers=_csrf(auth), json={"versionId": "cv-missing"}
    )
    assert created.status_code == 404


def test_reader_named_threads_are_version_scoped(client: TestClient) -> None:
    auth = _login(client, READER)
    _default_thread(client, auth)

    created = client.post(
        THREADS_PATH, headers=_csrf(auth),
        json={"title": "课堂讨论", "versionId": VERSION},
    )
    assert created.status_code == 201 and created.json()["versionId"] == VERSION
    renamed = client.patch(
        f"{THREADS_PATH}/{created.json()['id']}",
        headers=_csrf(auth), json={"title": "改标题"},
    )
    assert renamed.status_code == 200 and renamed.json()["versionId"] == VERSION
    listed = client.get(THREADS_PATH, params={"versionId": VERSION}).json()
    assert len(listed) == 2


def test_author_draft_context_stays_author_only(client: TestClient) -> None:
    reader = _login(client, READER)
    assert client.get(THREAD_PATH).status_code == 403
    assert client.post(
        THREADS_PATH, headers=_csrf(reader), json={"title": "x"}
    ).status_code == 403
    owner = _login(client, {"username": "admin", "password": "admin123"})
    snapshot = client.get(THREAD_PATH)
    assert snapshot.status_code == 200
    assert _send(client, owner, snapshot.json()["id"], "新 Run").status_code == 409


def test_cross_reader_threads_are_not_enumerable(client: TestClient) -> None:
    first = _login(client, READER)
    mine = _default_thread(client, first)["id"]

    with TestClient(client.app) as second_client:
        second = _second_reader(second_client)
        other = _default_thread(second_client, second)["id"]
        assert other != mine
        assert second_client.get(f"{THREADS_PATH}/{mine}").status_code == 404
        forged = _send(second_client, second, mine, "冒用他人线程")
        assert forged.status_code == 404
    assert client.get(f"{THREADS_PATH}/{other}").status_code == 404
    assert client.get(f"{THREADS_PATH}/{mine}").json()["id"] == mine


def test_reader_chat_run_completes_and_resumes(client: TestClient) -> None:
    auth = _login(client, READER)
    thread = _default_thread(client, auth)

    with agent.override(model=TestModel(custom_output_text="读者讨论回答")):
        response = _send(client, auth, thread["id"], "这个案例的教学设计如何？")

    assert response.status_code == 200
    run = client.app.state.database.agent_runs.find_one({}, {"_id": 0})
    assert run["status"] == "completed" and run["readOnly"] is True
    records = [row for row in run["resources"] if row["id"] == "agent/reader-agent"]
    assert records and records[0]["kind"] == "task-prompt"
    snapshot = client.get(f"{THREADS_PATH}/{thread['id']}").json()
    assert [item["role"] for item in snapshot["messages"]] == ["user", "assistant"]
    events = client.get(f"{THREAD_PATH}/{thread['id']}/events", params={"afterSeq": 0})
    assert events.status_code == 200
    assert '"delta":"读者讨论回答"' in events.text


def test_reader_cannot_select_case_edit_skill(client: TestClient) -> None:
    auth = _login(client, READER)
    thread = _default_thread(client, auth)

    response = _send(client, auth, thread["id"], "帮我改正文", skills=["case-edit-skill"])

    assert response.status_code == 422
    assert response.json() == {"detail": "AI 能力不可用"}


def test_reader_cannot_decide_artifacts(client: TestClient) -> None:
    reader = _login(client, READER)

    response = client.post(
        f"{THREAD_PATH}/thread-x/artifacts/artifact-x/decision",
        headers=_csrf(reader), json={"decision": "accepted"},
    )
    assert response.status_code == 403


def test_propose_tool_guard_blocks_readers_and_published_cases(client: TestClient) -> None:
    import pytest

    from app.modules.agent.artifacts import propose_artifact
    from app.modules.cases.service import CaseError

    database = client.app.state.database
    reader = _login(client, READER)["user"]
    with pytest.raises(CaseError) as forbidden:
        propose_artifact(database, CASE, "t1", "r1", 0, 1, "x", "", [], reader)
    assert forbidden.value.status_code == 403
    owner = _login(client, {"username": "admin", "password": "admin123"})["user"]
    with pytest.raises(CaseError) as conflict:
        propose_artifact(database, CASE, "t1", "r1", 0, 1, "x", "", [], owner)
    assert conflict.value.status_code == 409


def test_reader_capability_exposes_read_only_sources() -> None:
    capability = reader_capability()

    assert capability.defer_loading is False
    names = {
        getattr(tool, "name", None) or getattr(tool, "__name__", None)
        for tool in capability.tools
    }
    assert names == {"search_corpus", "read_source"}


def _assert_blocked(client: TestClient, auth: dict, thread_id: str) -> None:
    for request in (
        lambda: client.get(THREAD_PATH, params={"versionId": VERSION}),
        lambda: client.get(f"{THREADS_PATH}/{thread_id}"),
        lambda: client.post(f"{THREAD_PATH}/{thread_id}/cancel", headers=_csrf(auth)),
        lambda: client.get(f"{THREAD_PATH}/{thread_id}/events"),
    ):
        assert request().status_code == 404


def test_takedown_blocks_reader_threads_until_restored(client: TestClient) -> None:
    from tests.test_case_workflow import _transition_json, login

    auth = _login(client, READER)
    thread_id = _default_thread(client, auth)["id"]
    with TestClient(client.app) as admin_client:
        admin = login(admin_client).json()
        case = admin_client.get(f"/api/cases/{CASE}").json()
        hidden = _transition_json(admin_client, CASE, admin["csrfToken"], "hide", case)
        assert hidden["case"]["publicationStatus"] == "hidden"
        _assert_blocked(client, auth, thread_id)
        restored = _transition_json(
            admin_client, CASE, admin["csrfToken"], "restore", hidden["case"]
        )
    assert restored["case"]["publicationStatus"] == "public"
    assert client.get(f"{THREADS_PATH}/{thread_id}").status_code == 200


def _historical_version(database, title: str, number: int) -> dict:
    version = {
        "id": f"cv-historical-v{number}", "caseId": CASE, "number": number,
        "kind": "submission", "title": title, "summary": "",
        "document": {"type": "doc", "content": []}, "attachments": [],
        "materials": [], "metadata": {}, "sourceRevision": 90 + number,
        "createdBy": "u-admin-demo", "createdAt": "2026-09-07T00:00:00+00:00",
    }
    database.case_versions.insert_one(version)
    database.lifecycle_events.insert_one({
        "id": f"ce-historical-v{number}", "caseId": CASE, "action": "approve",
        "versionId": version["id"], "round": number, "actorId": "u-admin-demo",
        "actorRole": "admin", "createdAt": "2026-09-07T00:00:00+00:00",
    })
    return version


def test_historically_approved_versions_stay_readable(client: TestClient) -> None:
    historical = _historical_version(client.app.state.database, "历史批准版", 2)
    auth = _login(client, READER)

    bound = client.get(THREAD_PATH, params={"versionId": historical["id"]})

    assert bound.status_code == 200 and bound.json()["versionId"] == historical["id"]
    with agent.override(model=TestModel(custom_output_text="旧版回答")):
        response = _send(client, auth, bound.json()["id"], "继续旧版讨论")
    assert response.status_code == 200


def test_owner_history_stays_readable_while_new_runs_stay_blocked(client: TestClient) -> None:
    for case_id, account in (
        ("c-pending-1", READER), ("c-02", {"username": "admin", "password": "admin123"}),
    ):
        auth = _login(client, account)
        path = f"/api/cases/{case_id}/agent/thread"
        snapshot = client.get(path)
        thread_id = snapshot.json()["id"]
        assert snapshot.status_code == 200
        assert client.get(f"{path}/{thread_id}/events").status_code == 204
        assert client.post(
            f"{path}/{thread_id}/cancel", headers=_csrf(auth)
        ).json()["status"] == "idle"
        assert client.post(
            f"{path}/{thread_id}/stream", headers=_csrf(auth),
            json={"id": "writer", "trigger": "submit-message", "messages": [_message("新 Run")]},
        ).status_code == 409


def _version_mismatch_requests(client: TestClient, auth: dict, thread_id: str, wrong: str):
    return (
        lambda: client.get(f"{THREADS_PATH}/{thread_id}", params={"versionId": wrong}),
        lambda: client.patch(
            f"{THREADS_PATH}/{thread_id}", params={"versionId": wrong},
            headers=_csrf(auth), json={"title": "错配"},
        ),
        lambda: _send(client, auth, thread_id, "错配", version_id=wrong),
        lambda: client.post(
            f"{THREAD_PATH}/{thread_id}/stream?versionId={wrong}", headers=_csrf(auth),
            json={"id": "retry", "trigger": "regenerate-message", "messageId": "missing", "messages": []},
        ),
        lambda: client.post(
            f"{THREAD_PATH}/{thread_id}/cancel", params={"versionId": wrong}, headers=_csrf(auth),
        ),
        lambda: client.get(
            f"{THREAD_PATH}/{thread_id}/events", params={"versionId": wrong},
        ),
    )


def test_explicit_thread_version_mismatch_is_rejected(client: TestClient) -> None:
    auth = _login(client, READER)
    thread_id = _default_thread(client, auth)["id"]
    requests = _version_mismatch_requests(client, auth, thread_id, "cv-mismatch")
    assert [request().status_code for request in requests] == [409] * 6


def _gated_reader_model(reached: Event, release: Event):
    async def stream(_messages, _info):
        yield "前半"
        reached.set()
        await asyncio.to_thread(release.wait, 10)
        yield "后半"

    return FunctionModel(stream_function=stream)


def _reader_post_async(app, text: str, model):
    def send():
        with TestClient(app) as request_client:
            auth = _login(request_client, READER)
            with agent.override(model=model):
                return _send(request_client, auth, _default_thread(request_client, auth)["id"], text)

    pool = ThreadPoolExecutor(max_workers=1)
    return pool.submit(send), pool


def _hide_case(client: TestClient, case_id: str) -> None:
    admin = _login(client, {"username": "admin", "password": "admin123"})
    case = client.get(f"/api/cases/{case_id}").json()
    response = client.post(
        f"/api/cases/{case_id}/lifecycle", headers=_csrf(admin),
        json={"command": "hide", "revision": case["revision"]},
    )
    assert response.status_code == 200


def _paused_completion(original, entered: Event, release: Event):
    def paused(self, *args, **kwargs):
        assert kwargs["reader_case_id"] == CASE
        assert kwargs["reader_version_id"] == VERSION
        entered.set()
        assert release.wait(10)
        return original(self, *args, **kwargs)

    return paused


def _assert_reader_completion_cancelled(client: TestClient, future) -> None:
    response = future.result(timeout=15)
    run = client.app.state.database.agent_runs.find_one({}, {"_id": 0})
    assert response.status_code == 200 and run["status"] == "cancelled"
    assert client.app.state.database.agent_messages.count_documents({"role": "assistant"}) == 0
    assert not client.app.state.database.agent_thread_events.find_one({"type": "run.completed"})


def test_reader_stream_is_cancelled_when_publication_is_hidden(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(service, "RUN_HEARTBEAT_SECONDS", 0.01)
    auth = _login(client, READER)
    thread_id = _default_thread(client, auth)["id"]
    reached, release = Event(), Event()
    future, pool = _reader_post_async(client.app, "撤权测试", _gated_reader_model(reached, release))
    try:
        assert reached.wait(10)
        with TestClient(client.app) as admin_client:
            _hide_case(admin_client, CASE)
        release.set()
        response = future.result(timeout=15)
        run = client.app.state.database.agent_runs.find_one({"threadId": thread_id}, {"_id": 0})
        assert response.status_code == 200 and "后半" not in response.text
        assert run["status"] == "cancelled"
        assert client.app.state.database.agent_messages.count_documents({"threadId": thread_id, "role": "assistant"}) == 0
    finally:
        release.set()
        pool.shutdown(wait=True)


def test_reader_completion_rechecks_visibility_after_final_check(client, monkeypatch) -> None:
    entered, release = Event(), Event()
    original = AgentRepository.complete_run
    monkeypatch.setattr(AgentRepository, "complete_run", _paused_completion(original, entered, release))
    future, pool = _reader_post_async(client.app, "尾部撤权测试", TestModel(custom_output_text="回答"))
    try:
        assert entered.wait(10)
        with TestClient(client.app) as admin_client:
            _hide_case(admin_client, CASE)
        release.set()
        _assert_reader_completion_cancelled(client, future)
    finally:
        release.set()
        pool.shutdown(wait=True)
