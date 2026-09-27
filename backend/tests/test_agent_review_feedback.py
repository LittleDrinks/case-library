import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai.models.function import FunctionModel

from app.modules.agent.review_feedback import read_review_feedback
from app.modules.agent.runtime import agent
from app.modules.cases.lifecycle import get_review_feedback
from app.modules.cases.service import CaseError
from tests.test_agent_grounding import _auth, _stream_post, _tool_model
from tests.test_agent_review_chat import _csrf, _review_thread
from tests.test_case_workflow import _decide, _relogin, _review_round, _transition_json


def _reviewed_twice(client):
    admin, case, _, started = _review_round(client)
    versions = []
    for message in ["补充来源\n第一轮完整留言", "调整教学安排\n第二轮完整留言"]:
        versions.append(started["version"])
        result = _decide(client, admin, started, "reject",
                         reasonTypes=["内容需要补充或修改"], message=message)
        owner = _relogin(client)
        submitted = _transition_json(client, case["id"], owner["csrfToken"], "submit", result["case"])
        admin = _relogin(client, "admin", "admin123")
        started = _transition_json(client, case["id"], admin["csrfToken"], "start", submitted["case"])
    return versions, started, admin


@pytest.mark.parametrize("specified", [False, True])
@pytest.mark.parametrize("editable", [False, True])
def test_author_agent_reads_versioned_feedback_after_resubmission(client, specified, editable):
    versions, started, _ = _reviewed_twice(client)
    auth = _auth(client)
    if editable:
        _transition_json(client, "c-draft-1", auth["csrfToken"], "withdraw", started["case"])
    outputs = []
    args = {"version_number": versions[0]["number"]} if specified else {}
    model = _tool_model("read_review_feedback", args, "review-feedback", outputs, "已读取意见")
    response = _stream_post(client, auth, "c-draft-1", "feedback-request", "feedback-message",
                            [{"type": "text", "text": "读取审核意见"}], model)
    assert response.status_code == 200
    assert len(outputs) == 1
    expected = versions[0 if specified else 1]
    assert outputs[0]["status"] == "ok"
    assert outputs[0]["versionId"] == expected["id"]
    assert outputs[0]["versionNumber"] == expected["number"]
    assert outputs[0]["message"] == ("补充来源\n第一轮完整留言" if specified else "调整教学安排\n第二轮完整留言")
    assert outputs[0]["reasonTypes"] == ["内容需要补充或修改"]
    database = client.app.state.database
    assert database.cases.find_one({"id": "c-draft-1"}).get("lastReview") is None
    run = database.agent_runs.find_one({})
    assert run["status"] == "completed" and run["readOnly"] is not editable
    assert database.agent_writes.count_documents({}) == 0
    assert database.agent_artifacts.count_documents({}) == 0
    assert get_review_feedback(database, "c-draft-1", auth["user"], started["version"]["number"])["status"] == "empty"


def test_review_agent_reads_feedback_without_write_tools(client):
    versions, _, auth = _reviewed_twice(client)
    case_id = "c-draft-1"
    thread = _review_thread(client, auth, case_id)
    outputs = []
    model = _tool_model("read_review_feedback", {}, "review-feedback", outputs, "已读取上轮意见")
    with agent.override(model=model):
        response = client.post(
            f"/api/cases/{case_id}/agent/thread/{thread['id']}/stream", headers=_csrf(auth),
            json={"id": "feedback", "trigger": "submit-message", "messages": [
                {"id": "feedback-message", "role": "user", "parts": [{"type": "text", "text": "查看上轮意见"}]},
            ]},
        )
    assert response.status_code == 200
    assert outputs[0]["versionId"] == versions[-1]["id"]
    assert client.app.state.database.agent_runs.find_one({})["status"] == "completed"


def test_review_feedback_is_private_and_reports_absence(client):
    auth = _auth(client)
    database = client.app.state.database
    assert get_review_feedback(database, "c-draft-1", auth["user"])["status"] == "empty"
    with pytest.raises(CaseError) as error:
        get_review_feedback(database, "c-draft-1", {"id": "other", "role": "user"})
    assert error.value.status_code == 403
    context = SimpleNamespace(deps=SimpleNamespace(version_id="published-version"))
    assert asyncio.run(read_review_feedback(context))["status"] == "no_access"


@pytest.mark.parametrize("state", ["pending", "reviewing", "published"])
def test_locked_author_can_discuss_selection_with_read_only_tools(client, state):
    auth = _auth(client)
    database = client.app.state.database
    document = {"type": "doc", "content": [{"type": "paragraph", "content": [
        {"type": "text", "text": "需要解释的原文"},
    ]}]}
    database.cases.update_one({"id": "c-draft-1"}, {"$set": {"workflowStatus": state, "document": document}})
    seen = []

    async def capture(_messages, info):
        seen.append(info)
        yield "解释选中的原文"

    response = _stream_post(client, auth, "c-draft-1", "readonly", "selection", [
        {"type": "text", "text": "解释选中这段"},
        {"type": "data-selection", "data": {"from": 1, "to": 5, "quote": "伪造选区"}},
    ], FunctionModel(stream_function=capture))
    assert response.status_code == 200
    assert "需要解释" in seen[0].instructions and "伪造选区" not in seen[0].instructions
    names = {tool.name for tool in seen[0].function_tools}
    assert "read_review_feedback" in names
    assert not names & {"propose_revision", "propose_document", "write_document"}
    assert database.agent_runs.find_one({})["status"] == "completed"
    assert database.agent_runs.find_one({})["readOnly"] is True
    assert database.cases.find_one({"id": "c-draft-1"})["document"] == document


def test_retry_after_submission_stays_read_only(client):
    auth = _auth(client)

    async def fail(_messages, _info):
        raise RuntimeError("模拟服务中断")
        yield ""

    _stream_post(client, auth, "c-draft-1", "failed-request", "failed-message",
                 [{"type": "text", "text": "解释案例"}], FunctionModel(stream_function=fail))
    database = client.app.state.database
    failed = database.agent_runs.find_one({})
    assert failed["status"] == "failed"
    database.cases.update_one({"id": "c-draft-1"}, {"$set": {"workflowStatus": "pending"}})

    async def answer(_messages, info):
        assert "propose_revision" not in {tool.name for tool in info.function_tools}
        yield "只读解释"

    with agent.override(model=FunctionModel(stream_function=answer)):
        response = client.post(
            f"/api/cases/c-draft-1/agent/thread/{failed['threadId']}/stream", headers=_csrf(auth),
            json={"id": "retry", "trigger": "regenerate-message",
                  "messageId": failed["userMessageId"], "messages": []},
        )
    assert response.status_code == 200
    retried = database.agent_runs.find_one({"id": {"$ne": failed["id"]}})
    assert retried["status"] == "completed" and retried["readOnly"] is True
