"""已发布 Skill 驱动真实 Run：选择、按需加载、资源读取、版本绑定与哈希记录。"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient
from pydantic_ai import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from app.modules.agent.runtime import agent
from app.modules.agent.skills import resource_tool_name
from app.modules.skills.service import BoundSkill, bind_published_skill
from tests.skill_packages import (
    EXAMPLE_PATH,
    EXAMPLE_TEXT,
    FILES,
    SKILL_DIR,
    SKILL_ID,
    build_package,
)

CASES_PATH = "/api/cases"
ADMIN = {"username": "admin", "password": "admin123"}
TEACHER = {"username": "user", "password": "user123"}
RESOURCE_PATH = EXAMPLE_PATH


def _login(client: TestClient, account: dict) -> dict:
    response = client.post("/api/auth/login", json=account)
    assert response.status_code == 200
    return response.json()


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _package(version: int) -> bytes:
    files = dict(FILES)
    files[f"{SKILL_DIR}/SKILL.md"] = files[f"{SKILL_DIR}/SKILL.md"].replace(
        "# 习近平文化思想课程思政案例生成技能",
        f"# 习近平文化思想课程思政案例生成技能 v{version}",
    )
    return build_package(files)


def _upload_and_publish(client: TestClient, version: int = 1) -> dict:
    admin = _login(client, ADMIN)
    response = client.post(
        "/api/admin/skills/packages", headers=_csrf(admin),
        files={"file": (f"skill-v{version}.zip", _package(version), "application/zip")},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    publish = client.post(
        f"/api/admin/skills/{SKILL_ID}/publish", headers=_csrf(admin),
        json={"versionId": payload["version"]["id"]},
    )
    assert publish.status_code == 200, publish.text
    return payload["version"]


def _upload_only(client: TestClient) -> None:
    admin = _login(client, ADMIN)
    response = client.post(
        "/api/admin/skills/packages", headers=_csrf(admin),
        files={"file": ("skill.zip", _package(1), "application/zip")},
    )
    assert response.status_code == 201, response.text


def _create_case(client: TestClient, auth: dict) -> dict:
    response = client.post(
        CASES_PATH, headers=_csrf(auth),
        json={
            "title": "skill 案例",
            "document": {"type": "doc", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "第一段。"}]},
            ]},
        },
    )
    assert response.status_code == 200
    return response.json()


def _skill_model(skill_id: str, tool_name: str) -> FunctionModel:
    """依次调用 load_capability 与资源读取工具，驱动真实 Skill 链路。

    issued 记录本次发送已发出的调用，跨模型请求步进且不受历史 Run 影响。
    """
    issued: list[str] = []

    async def stream(messages, _info):
        response = _next_skill_step(issued, skill_id, tool_name)
        async for delta in _stream_deltas(response):
            yield delta

    return FunctionModel(stream_function=stream)


def _failing_skill_model(skill_id: str) -> FunctionModel:
    """先加载能力再提供方失败：验证失败 Run 保留创建时固化的版本凭据。"""
    issued: list[str] = []

    async def stream(_messages, _info):
        if "load_capability" not in issued:
            issued.append("load_capability")
            response = ModelResponse(parts=[ToolCallPart(
                tool_name="load_capability", args={"id": skill_id},
            )])
        else:
            raise RuntimeError("provider unavailable")
        async for delta in _stream_deltas(response):
            yield delta

    return FunctionModel(stream_function=stream)


def _gated_skill_model(skill_id: str, reached: Event, release: Event) -> FunctionModel:
    """加载能力后阻塞：证明凭据先于提供方执行落库，且取消后仍保留。"""
    issued: list[str] = []

    async def stream(_messages, _info):
        if "load_capability" not in issued:
            issued.append("load_capability")
            response = ModelResponse(parts=[ToolCallPart(
                tool_name="load_capability", args={"id": skill_id},
            )])
        else:
            reached.set()
            await asyncio.to_thread(release.wait, 60)
            response = ModelResponse(parts=[TextPart(content="不应到达")])
        async for delta in _stream_deltas(response):
            yield delta

    return FunctionModel(stream_function=stream)


def _next_skill_step(issued: list[str], skill_id: str, tool_name: str) -> ModelResponse:
    if "load_capability" not in issued:
        issued.append("load_capability")
        return ModelResponse(parts=[ToolCallPart(
            tool_name="load_capability", args={"id": skill_id},
        )])
    if tool_name not in issued:
        issued.append(tool_name)
        return ModelResponse(parts=[ToolCallPart(
            tool_name=tool_name, args={"path": RESOURCE_PATH},
        )])
    return ModelResponse(parts=[TextPart(content="已读取范例并起草。")])


async def _stream_deltas(response: ModelResponse):
    for index, part in enumerate(response.parts):
        if isinstance(part, TextPart):
            yield part.content
        else:
            yield {0: DeltaToolCall(
                name=part.tool_name, json_args=json.dumps(part.args_as_dict()),
                tool_call_id=part.tool_call_id or f"delta-{index}",
            )}


def _placeholder_tool_name(skill_id: str) -> str:
    bound = BoundSkill(
        skill_id=skill_id, version_id="v", version="v1", package_sha256="0" * 64,
        store=None, body="", description="", entry_path="", root="", files=(),
    )
    return resource_tool_name(bound)


def _send_message(
    client: TestClient, auth: dict, case_id: str, skill_id: str | None,
    model: FunctionModel | None = None,
):
    parts = [{"type": "text", "text": "请按范例写一份教学设计"}]
    if skill_id:
        parts.append({"type": "data-skill", "data": {"skillId": skill_id}})
    thread_id = client.get(f"{CASES_PATH}/{case_id}/agent/thread").json()["id"]
    if model is None:
        model = _skill_model(
            skill_id or "unused", _placeholder_tool_name(skill_id or "unused")
        )
    with agent.override(model=model):
        return client.post(
            f"{CASES_PATH}/{case_id}/agent/thread/{thread_id}/stream",
            headers=_csrf(auth),
            json={
                "id": f"browser-{uuid.uuid4().hex}", "trigger": "submit-message",
                "messages": [{
                    "id": f"client-{uuid.uuid4().hex}", "role": "user",
                    "parts": parts,
                }],
            },
        )


def _run_rows(database) -> list[dict]:
    return list(database.agent_runs.find({}, {"_id": 0, "resources": 1}).sort("_id", 1))


def _await_run(database, thread_id: str, status: str | None = None,
               deadline: float = 10) -> dict:
    end = time.monotonic() + deadline
    query: dict = {"threadId": thread_id}
    if status:
        query["status"] = status
    while time.monotonic() < end:
        run = database.agent_runs.find_one(query, {"_id": 0})
        if run:
            return run
        Event().wait(0.02)
    raise AssertionError(f"run not found: status={status}")


def _binding_record(version: dict) -> dict:
    return {
        "kind": "skill", "id": SKILL_ID,
        "versionId": version["id"], "version": version["version"],
    }


def test_published_skill_drives_run_and_records_version_hash(client: TestClient) -> None:
    version = _upload_and_publish(client)
    teacher = _login(client, TEACHER)
    case = _create_case(client, teacher)
    response = _send_message(client, teacher, case["id"], SKILL_ID)
    assert response.status_code == 200, response.text
    run = _run_rows(client.app.state.database)[0]
    records = {row["kind"]: row for row in run["resources"]}
    assert records["skill"] == {
        "kind": "skill", "id": SKILL_ID,
        "version": version["version"], "contentHash": version["packageSha256"],
    }
    load, reader = _tool_parts(client, case["id"])
    assert load["input"]["id"] == SKILL_ID
    assert reader["output"]["content"] == EXAMPLE_TEXT
    assert reader["output"]["path"] == RESOURCE_PATH


def _tool_parts(client: TestClient, case_id: str) -> tuple[dict, dict]:
    snapshot = client.get(f"{CASES_PATH}/{case_id}/agent/thread").json()
    parts = [
        part for message in snapshot["messages"] for part in message["parts"]
        if part["type"].startswith("tool-")
    ]
    kinds = [part["type"] for part in parts]
    assert kinds[0] == "tool-load_capability" and len(kinds) == 2, kinds
    return parts[0], parts[1]


def test_new_run_resolves_new_publication_and_old_run_stays(client: TestClient) -> None:
    v1 = _upload_and_publish(client, 1)
    case = _create_case(client, _login(client, TEACHER))
    assert _send_message(client, _login(client, TEACHER), case["id"], SKILL_ID).status_code == 200
    v2 = _upload_and_publish(client, 2)
    assert v2["packageSha256"] != v1["packageSha256"]
    assert _send_message(client, _login(client, TEACHER), case["id"], SKILL_ID).status_code == 200
    runs = _run_rows(client.app.state.database)
    assert [row["resources"][-1]["contentHash"] for row in runs] == [
        v1["packageSha256"], v2["packageSha256"],
    ]
    assert [row["resources"][-1]["version"] for row in runs] == ["v1", "v2"]


def test_unpublished_or_unknown_skill_rejected_before_run(client: TestClient) -> None:
    _upload_only(client)
    teacher = _login(client, TEACHER)
    case = _create_case(client, teacher)
    response = _send_message(client, teacher, case["id"], SKILL_ID)
    assert response.status_code == 422
    assert response.json()["detail"] == "AI 能力不可用"
    database = client.app.state.database
    assert database.agent_runs.count_documents({}) == 0
    assert database.agent_messages.count_documents({}) == 0
    assert _send_message(client, teacher, case["id"], "fake-skill").status_code == 422


def test_baseline_without_skill_selection_stays_intact(client: TestClient) -> None:
    teacher = _login(client, TEACHER)
    case = _create_case(client, teacher)
    response = _send_message(client, teacher, case["id"], None)
    assert response.status_code == 200, response.text
    run = _run_rows(client.app.state.database)[0]
    assert {row["kind"] for row in run["resources"]} == {"system-prompt", "task-prompt"}


def test_bound_snapshot_reads_stored_package_bytes(client: TestClient) -> None:
    version = _upload_and_publish(client)
    bound = bind_published_skill(
        client.app.state.database, client.app.state.blob_store, SKILL_ID
    )
    assert bound.version_id == version["id"]
    assert bound.read_resource(RESOURCE_PATH) == EXAMPLE_TEXT
    assert bound.resource_record()["contentHash"] == version["packageSha256"]


def test_binding_persisted_before_provider_execution_and_survives_cancel(
    client: TestClient,
) -> None:
    version = _upload_and_publish(client)
    teacher = _login(client, TEACHER)
    case = _create_case(client, teacher)
    database = client.app.state.database
    reached, release = Event(), Event()
    model = _gated_skill_model(SKILL_ID, reached, release)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_send_message, client, teacher, case["id"], SKILL_ID, model)
        try:
            thread_id = client.get(f"{CASES_PATH}/{case['id']}/agent/thread").json()["id"]
            assert reached.wait(10), "model did not reach the gated step"
            # 提供方仍阻塞在第二步：版本凭据已随 Run 创建固化，成功完成前即可审计。
            run = _await_run(database, thread_id, status="active")
            assert run["skillBindings"] == [_binding_record(version)]

            cancelled = client.post(
                f"{CASES_PATH}/{case['id']}/agent/thread/{thread_id}/cancel",
                headers=_csrf(teacher),
            )
            assert cancelled.status_code == 200
            terminal = _await_run(database, thread_id, status="cancelled")
            assert terminal["skillBindings"] == [_binding_record(version)]
            assert terminal.get("resources", []) == []
        finally:
            release.set()
            future.result(timeout=15)


def test_failed_run_and_retry_keep_version_receipts(client: TestClient) -> None:
    """失败 Run 保留 v1 凭据；重试是新 Run，固化当时已发布的 v2 凭据。"""
    v1 = _upload_and_publish(client, 1)
    teacher = _login(client, TEACHER)
    case = _create_case(client, teacher)
    database = client.app.state.database
    failed_response = _send_message(
        client, teacher, case["id"], SKILL_ID,
        model=_failing_skill_model(SKILL_ID),
    )
    assert failed_response.status_code == 200, failed_response.text
    thread_id = client.get(f"{CASES_PATH}/{case['id']}/agent/thread").json()["id"]
    failed = _await_run(database, thread_id, status="failed")
    assert failed["skillBindings"] == [_binding_record(v1)]

    v2 = _upload_and_publish(client, 2)
    assert v2["packageSha256"] != v1["packageSha256"]
    teacher = _login(client, TEACHER)  # 管理员登录会替换共享会话 cookie，需重取教师会话
    user_message = database.agent_messages.find_one(
        {"threadId": thread_id, "role": "user"}, {"_id": 0}
    )
    with agent.override(model=_skill_model(SKILL_ID, _placeholder_tool_name(SKILL_ID))):
        retried_response = client.post(
            f"{CASES_PATH}/{case['id']}/agent/thread/{thread_id}/stream",
            headers=_csrf(teacher),
            json={
                "id": f"browser-{uuid.uuid4().hex}",
                "trigger": "regenerate-message",
                "messageId": user_message["id"],
                "messages": [],
            },
        )
    assert retried_response.status_code == 200, retried_response.text
    retried = _await_run(database, thread_id, status="completed")
    assert retried["id"] != failed["id"]
    assert retried["skillBindings"] == [_binding_record(v2)]
    # 历史 Run 的凭据不受新发布影响。
    assert database.agent_runs.find_one(
        {"id": failed["id"]}, {"_id": 0, "skillBindings": 1}
    )["skillBindings"] == [_binding_record(v1)]
    records = {row["kind"]: row for row in retried["resources"]}
    assert {key: records["skill"][key] for key in ("kind", "id", "version")} == {
        "kind": "skill", "id": SKILL_ID, "version": v2["version"],
    }
