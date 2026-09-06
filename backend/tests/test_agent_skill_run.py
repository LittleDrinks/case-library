"""已发布 Skill 驱动真实 Run：选择、按需加载、资源读取、版本绑定与哈希记录。"""

from __future__ import annotations

import json
import uuid

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


def _send_message(client: TestClient, auth: dict, case_id: str, skill_id: str | None):
    parts = [{"type": "text", "text": "请按范例写一份教学设计"}]
    if skill_id:
        parts.append({"type": "data-skill", "data": {"skillId": skill_id}})
    thread_id = client.get(f"{CASES_PATH}/{case_id}/agent/thread").json()["id"]
    model = _skill_model(skill_id or "unused", _placeholder_tool_name(skill_id or "unused"))
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
