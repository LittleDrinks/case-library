"""Issue241 管理员审核只读私人 AI 对话：身份、隔离与服务端只读链路。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from app.modules.agent.runtime import agent
from tests.skill_packages import SKILL_ID
from tests.test_agent_skill_run import (
    _placeholder_tool_name,
    _recording_skill_model,
    _upload_and_publish,
)

CASE = "c-pending-1"
DRAFT_TEXT = "学生作业中存在生成式人工智能代写痕迹"
REVIEW_TAG_CONTEXT = (
    "当前案例 tagIds 按现有标签组解析的名称",
    "学科：工学", "课程：中国近现代史纲要",
    "案例类型：课堂教学类", "思政元素：劳动教育",
)
THREAD_PATH = f"/api/cases/{CASE}/agent/thread"
THREADS_PATH = f"/api/cases/{CASE}/agent/threads"
ADMIN = {"username": "admin", "password": "admin123"}
AUTHOR = {"username": "user", "password": "user123"}


def _login(client: TestClient, account: dict) -> dict:
    response = client.post("/api/auth/login", json=account)
    assert response.status_code == 200
    return response.json()


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _start_review(client: TestClient, case_id: str = CASE) -> dict:
    """管理员对待审案例开始审核：审核对话仅在 pending/reviewing 状态可用。"""
    from tests.test_case_workflow import _transition_json, login

    with TestClient(client.app) as admin_client:
        auth = login(admin_client).json()
        case = admin_client.get(f"/api/cases/{case_id}").json()
        result = _transition_json(
            admin_client, case_id, auth["csrfToken"], "start", case
        )
    assert result["case"]["workflowStatus"] == "reviewing"
    return result["case"]


def _review_thread(client: TestClient, auth: dict, case_id: str = CASE) -> dict:
    response = client.get(
        f"/api/cases/{case_id}/agent/thread", params={"mode": "review"}
    )
    assert response.status_code == 200
    return response.json()


def _send(client: TestClient, auth: dict, thread_id: str, text: str, **params) -> object:
    return client.post(
        f"{THREAD_PATH}/{thread_id}/stream", headers=_csrf(auth),
        params=params,
        json={
            "id": "review-chat", "trigger": "submit-message",
            "messages": [{"id": "m1", "role": "user",
                          "parts": [{"type": "text", "text": text}]}],
        },
    )


def test_review_thread_binds_draft_and_isolates_identities(client: TestClient) -> None:
    _start_review(client)
    admin = _login(client, ADMIN)
    mine = _review_thread(client, admin)

    assert mine["versionId"] is None and mine["caseId"] == CASE
    assert _review_thread(client, admin)["id"] == mine["id"]
    listed = client.get(THREADS_PATH, params={"mode": "review"}).json()
    assert [item["id"] for item in listed] == [mine["id"]]
    _login(client, AUTHOR)
    assert client.get(THREAD_PATH, params={"mode": "review"}).status_code == 403
    assert client.get(f"{THREADS_PATH}/{mine['id']}").status_code == 404


def test_demoted_admin_cannot_restore_review_thread(client: TestClient) -> None:
    """已公开案例上恢复审核线程仍要求管理员：防降权后凭线程所有权续用。"""
    database = client.app.state.database
    database.cases.update_one(
        {"id": CASE},
        {"$set": {"workflowStatus": "reviewing", "publicationStatus": "public"}},
    )
    admin = _login(client, ADMIN)
    thread_id = _review_thread(client, admin)["id"]
    database.users.update_one(
        {"id": admin["user"]["id"]}, {"$set": {"role": "user"}}
    )
    assert client.get(f"{THREADS_PATH}/{thread_id}").status_code == 403


def _skill_reject_response(client: TestClient, auth: dict, thread_id: str) -> object:
    parts = [{"type": "text", "text": "帮我改进"},
             {"type": "data-skill", "data": {"skillId": "case-edit-skill"}}]
    return client.post(
        f"{THREAD_PATH}/{thread_id}/stream", headers=_csrf(auth),
        json={"id": "c1", "trigger": "submit-message",
              "messages": [{"id": "m1", "role": "user", "parts": parts}]},
    )


def test_review_run_is_server_side_read_only(client: TestClient) -> None:
    _start_review(client)
    admin = _login(client, ADMIN)
    thread = _review_thread(client, admin)
    assert _skill_reject_response(client, admin, thread["id"]).status_code == 422

    with agent.override(model=TestModel(custom_output_text="审核讨论回答")):
        response = _send(client, admin, thread["id"], "总结这篇待审稿的问题")
    assert response.status_code == 200
    run = client.app.state.database.agent_runs.find_one({}, {"_id": 0})
    assert run["status"] == "completed"
    assert run["readOnly"] is True and run["writeAuthorized"] is False
    assert run.get("baseRevision") is None and run.get("target") is None
    prompts = [row["id"] for row in run["resources"] if row["kind"] == "task-prompt"]
    assert prompts == ["agent/review-agent"]


def test_restored_review_thread_cannot_escalate_write(client: TestClient) -> None:
    from app.modules.agent.writes import direct_write_requested

    prompt = "我要直接写入正文，立即执行"
    assert direct_write_requested(prompt) is True
    _start_review(client)
    admin = _login(client, ADMIN)
    thread_id = _review_thread(client, admin)["id"]
    assert client.get(f"{THREADS_PATH}/{thread_id}").json()["id"] == thread_id
    with agent.override(model=TestModel(custom_output_text="只读回答")):
        response = _send(client, admin, thread_id, prompt)
    assert response.status_code == 200
    run = client.app.state.database.agent_runs.find_one({"threadId": thread_id})
    assert run["writeAuthorized"] is False and run["readOnly"] is True
    assert client.app.state.database.agent_writes.count_documents({}) == 0


def test_review_instructions_come_from_pending_draft(client: TestClient) -> None:
    seen: list[str] = []

    async def _capture(_messages, info):
        seen.append(info.instructions or "")
        yield "根据待审稿回答"

    _start_review(client)
    admin = _login(client, ADMIN)
    thread = _review_thread(client, admin)
    with agent.override(model=FunctionModel(stream_function=_capture)):
        assert _send(client, admin, thread["id"], "这篇待审稿讲什么").status_code == 200
    instructions = seen[0]
    assert "案例审核讨论助手" in instructions and DRAFT_TEXT in instructions
    assert "协助案例作者修订和撰写正文" not in instructions


def _send_parts(client: TestClient, auth: dict, thread_id: str, parts: list[dict]) -> object:
    return client.post(
        f"{THREAD_PATH}/{thread_id}/stream", headers=_csrf(auth),
        json={"id": "c1", "trigger": "submit-message",
              "messages": [{"id": "m1", "role": "user", "parts": parts}]},
    )


def _review_skill_parts() -> list[dict]:
    return [{"type": "text", "text": "请按审核维度核查这篇待审稿"},
            {"type": "data-skill", "data": {"skillId": SKILL_ID}}]


def _review_run_receipt(client: TestClient, thread_id: str) -> tuple[list, dict]:
    calls: list = []
    model = _recording_skill_model(SKILL_ID, _placeholder_tool_name(SKILL_ID), calls)
    with agent.override(model=model):
        response = _send_parts(client, _login(client, ADMIN), thread_id, _review_skill_parts())
    assert response.status_code == 200, response.text
    return calls, client.app.state.database.agent_runs.find_one(
        {"threadId": thread_id}, {"_id": 0}
    )


def test_review_run_loads_published_skill_and_stays_read_only(client: TestClient) -> None:
    """审核对话可加载已发布 Skill：版本绑定入账，写工具与产物仍不可用。"""
    version = _upload_and_publish(client)
    _start_review(client)
    thread = _review_thread(client, _login(client, ADMIN))
    calls, run = _review_run_receipt(client, thread["id"])
    database = client.app.state.database
    assert run["status"] == "completed"
    assert run["readOnly"] is True and run["writeAuthorized"] is False
    assert run["skillBindings"] == [{
        "kind": "skill", "id": SKILL_ID,
        "versionId": version["id"], "version": version["version"],
    }]
    records = {row["kind"]: row for row in run["resources"]}
    assert records["skill"]["contentHash"] == version["packageSha256"]
    assert database.agent_artifacts.count_documents({}) == 0
    assert database.agent_writes.count_documents({}) == 0
    later = [str(part) for message in calls[-1][0] for part in message.parts]
    assert any("写作前至少通读一个范例" in text for text in later)


def _tagged_review_case(client: TestClient, fields: dict) -> None:
    client.app.state.database.cases.update_one({"id": CASE}, {"$set": fields})


def test_review_instructions_resolve_case_tag_names_by_group(client: TestClient) -> None:
    """审核上下文注入当前案例真实标签名称与所属组，缺失时模型不得猜标签。"""
    _tagged_review_case(client, {"tagIds": [
        "tag-seed-1-4", "tag-seed-2-2", "tag-seed-3-3", "tag-seed-4-4",
    ]})
    _start_review(client)
    seen: list[str] = []
    _capture_review_instructions(client, _login(client, ADMIN), seen)
    for marker in REVIEW_TAG_CONTEXT:
        assert marker in seen[0]


def _capture_review_instructions(client: TestClient, admin: dict, seen: list[str]) -> None:
    async def _capture(_messages, info):
        seen.append(info.instructions or "")
        yield "结合服务端上下文回答"

    thread = _review_thread(client, admin)
    with agent.override(model=FunctionModel(stream_function=_capture)):
        assert _send(client, admin, thread["id"], "结合上下文核查这篇待审稿").status_code == 200


def _seed_custom_review_tags(database) -> None:
    database.tag_groups.insert_many([
        {"id": "tgg-classroom", "name": "适用课堂", "requiredForSubmission": False,
         "sortKey": 9, "enabled": True},
        {"id": "tgg-stage", "name": "学习阶段", "requiredForSubmission": False,
         "sortKey": 10, "enabled": True},
    ])
    database.tags.insert_many([
        {"id": "tag-classroom-1", "groupId": "tgg-classroom", "name": "课程思政示范课",
         "sortKey": 0, "enabled": True},
        {"id": "tag-stage-1", "groupId": "tgg-stage", "name": "研究生阶段",
         "sortKey": 0, "enabled": True},
    ])


def test_review_context_lists_custom_groups_over_legacy_fields(client: TestClient) -> None:
    """审核上下文按实际标签组名（含自定义组）列出标签；与旧字段冲突时以真实 Tag 为准。"""
    _seed_custom_review_tags(client.app.state.database)
    _tagged_review_case(client, {
        "tagIds": ["tag-classroom-1", "tag-stage-1"],
        "course": "军事理论", "audience": "ug", "typeName": "人物传记类",
    })
    _start_review(client)
    seen: list[str] = []
    _capture_review_instructions(client, _login(client, ADMIN), seen)
    assert "适用课堂：课程思政示范课" in seen[0]
    assert "学习阶段：研究生阶段" in seen[0]
    for legacy in ("课程：军事理论", "课程：自然辩证法概论", "案例类型：人物传记类",
                   "案例类型：社会热点与治理类", "适用对象：本科", "适用对象：研究生"):
        assert legacy not in seen[0]


def test_review_context_states_missing_tags_instead_of_guessing(client: TestClient) -> None:
    """无任何标签时审核上下文明示不足，不退回旧课程/受众字段推断课堂适用性。"""
    client.app.state.database.cases.update_one(
        {"id": CASE},
        {"$unset": {"tagIds": "", "course": "", "audience": "", "typeName": "",
                    "purpose": "", "theoryPoints": "", "stageText": ""}},
    )
    _start_review(client)
    seen: list[str] = []
    _capture_review_instructions(client, _login(client, ADMIN), seen)
    assert "未选择任何标签" in seen[0]
    assert "标签一致性与课堂适用性缺少依据" in seen[0]
    for legacy in ("课程：", "案例类型：", "适用对象：", "教学用途：", "理论/思政要点："):
        assert legacy not in seen[0]
