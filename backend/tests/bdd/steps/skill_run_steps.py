"""Skill运行绑定场景步骤。"""
from __future__ import annotations

import json
import time
import uuid

from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from pytest_bdd import given, parsers, then, when

from app.modules.agent.runtime import agent
from app.modules.agent.skills import resource_tool_name
from app.modules.skills.service import BoundSkill
from tests.bdd.steps.common_steps import client_of, create_case, csrf_headers, login_as
from tests.skill_packages import (
    EXAMPLE_PATH, FILES, SKILL_DIR, SKILL_ID, SKILL_MD, build_package,
)

RESOURCE_PATH = EXAMPLE_PATH


def _placeholder_tool_name(skill_id: str) -> str:
    bound = BoundSkill(
        skill_id=skill_id, version_id="v", version="v1", package_sha256="0" * 64,
        store=None, body="", description="", entry_path="", root="", files=(),
    )
    return resource_tool_name(bound)


async def _stream_deltas(response: ModelResponse):
    for index, part in enumerate(response.parts):
        if isinstance(part, TextPart):
            yield part.content
        else:
            yield {0: DeltaToolCall(
                name=part.tool_name, json_args=json.dumps(part.args_as_dict()),
                tool_call_id=part.tool_call_id or f"delta-{index}",
            )}


def _skill_model(skill_id: str, tool_name: str) -> FunctionModel:
    """依次调用 load_capability 与资源读取工具，驱动真实 Skill 链路。"""
    issued: list[str] = []

    async def stream(messages, _info):
        if "load_capability" not in issued:
            issued.append("load_capability")
            response = ModelResponse(parts=[ToolCallPart(
                tool_name="load_capability", args={"id": skill_id})])
        elif tool_name not in issued:
            issued.append(tool_name)
            response = ModelResponse(parts=[ToolCallPart(
                tool_name=tool_name, args={"path": RESOURCE_PATH})])
        else:
            response = ModelResponse(parts=[TextPart(content="已读取范例并起草。")])
        async for delta in _stream_deltas(response):
            yield delta

    return FunctionModel(stream_function=stream)


def _upload_and_publish(ctx, version: int = 1) -> dict:
    login_as(ctx, "管理员")
    # 各版本包内容不同，保证 contentHash 可区分（对齐既有 _package(version)）。
    files = dict(FILES)
    files[f"{SKILL_DIR}/SKILL.md"] = SKILL_MD.replace(
        "# 习近平文化思想课程思政案例生成技能",
        f"# 习近平文化思想课程思政案例生成技能 v{version}",
    )
    upload = client_of(ctx).post(
        "/api/admin/skills/packages", headers=csrf_headers(ctx, "管理员"),
        files={"file": (f"skill-v{version}.zip", build_package(files),
                        "application/zip")},
    )
    assert upload.status_code == 201, upload.text
    payload = upload.json()
    publish = client_of(ctx).post(
        f"/api/admin/skills/{SKILL_ID}/publish", headers=csrf_headers(ctx, "管理员"),
        json={"versionId": payload["version"]["id"]},
    )
    assert publish.status_code == 200, publish.text
    return payload["version"]


def _upload_only(ctx) -> None:
    login_as(ctx, "管理员")
    upload = client_of(ctx).post(
        "/api/admin/skills/packages", headers=csrf_headers(ctx, "管理员"),
        files={"file": ("skill.zip", build_package(), "application/zip")},
    )
    assert upload.status_code == 201, upload.text


def _send_with_skill(ctx, skill_id: str):
    case_id = ctx["memo"]["current_case_id"]
    thread_id = client_of(ctx).get(
        f"/api/cases/{case_id}/agent/thread", headers=csrf_headers(ctx, "教师")
    ).json()["id"]
    ctx["memo"]["skill_thread_id"] = thread_id
    model = _skill_model(skill_id, _placeholder_tool_name(skill_id))
    parts = [
        {"type": "text", "text": "请按范例写一份教学设计"},
        {"type": "data-skill", "data": {"skillId": skill_id}},
    ]
    with agent.override(model=model):
        response = client_of(ctx).post(
            f"/api/cases/{case_id}/agent/thread/{thread_id}/stream",
            headers=csrf_headers(ctx, "教师"),
            json={"id": f"browser-{uuid.uuid4().hex}", "trigger": "submit-message",
                  "messages": [{"id": f"client-{uuid.uuid4().hex}", "role": "user",
                                "parts": parts}]},
        )
    ctx["memo"]["last_response"] = response
    return response


def _await_terminal_run(ctx, thread_id: str, deadline: float = 10) -> dict | None:
    database = client_of(ctx).app.state.database
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        runs = list(database.agent_runs.find(
            {"threadId": thread_id, "status": {"$ne": "active"}}, {"_id": 0}))
        if runs:
            return runs[-1]
        time.sleep(0.02)
    return None


@given("管理员已上传并发布Skill包")
def published_skill_exists(ctx):
    ctx["memo"]["skill_version"] = _upload_and_publish(ctx)


@given("管理员已上传但未发布Skill包")
def uploaded_skill_not_published(ctx):
    _upload_only(ctx)


@when("教师绑定该Skill发起对话")
def teacher_runs_skill(ctx):
    login_as(ctx, "教师")
    create_case(ctx, "教师", f"Skill运行案例 {time.time()}", "讨论正文")
    ctx["memo"]["last_response"] = _send_with_skill(ctx, SKILL_ID)
    if ctx["memo"]["last_response"].status_code == 200:
        run = _await_terminal_run(ctx, ctx["memo"]["skill_thread_id"])
        assert run and run["status"] == "completed", run
        ctx["memo"].setdefault("skill_run_ids", []).append(run["id"])
        ctx["memo"].setdefault("skill_run_hashes", []).append(
            ctx["memo"]["skill_version"]["packageSha256"]
        )


@then("绑定被拒绝且不产生运行记录")
def binding_rejected_no_run(ctx):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "AI 能力不可用"
    database = client_of(ctx).app.state.database
    assert database.agent_runs.count_documents({}) == 0


@when("教师已用该Skill完成一次对话")
def teacher_first_skill_run(ctx):
    teacher_runs_skill(ctx)


@when("管理员上传并发布新版Skill包")
def admin_publishes_new_version(ctx):
    ctx["memo"]["skill_version"] = _upload_and_publish(ctx, version=2)


@when("教师再次绑定Skill发起对话")
def teacher_second_skill_run(ctx):
    teacher_runs_skill(ctx)


@then(parsers.parse("运行资源记录Skill版本与内容哈希"))
def run_records_version_hash(ctx):
    version = ctx["memo"]["skill_version"]
    database = client_of(ctx).app.state.database
    run = database.agent_runs.find_one({"id": ctx["memo"]["skill_run_ids"][-1]})
    assert run["status"] == "completed"
    records = {row["kind"]: row for row in run["resources"]}
    assert records["skill"]["id"] == SKILL_ID
    assert records["skill"]["version"] == version["version"]
    assert records["skill"]["contentHash"] == version["packageSha256"]


@then("两次运行分别记录新旧版本哈希")
def two_runs_record_both_hashes(ctx):
    version = ctx["memo"]["skill_version"]
    database = client_of(ctx).app.state.database
    runs = list(database.agent_runs.find({"id": {"$in": ctx["memo"]["skill_run_ids"]}})
                .sort("_id", 1))
    assert len(runs) == 2, runs
    assert all(run["status"] == "completed" for run in runs), runs
    hashes = [next(row["contentHash"] for row in run["resources"] if row["kind"] == "skill")
              for run in runs]
    assert hashes == ctx["memo"]["skill_run_hashes"]
    assert hashes[0] != hashes[1]
    assert hashes[-1] == version["packageSha256"]
