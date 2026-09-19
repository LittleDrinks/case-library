"""案例生命周期场景步骤。"""
from __future__ import annotations

from pytest_bdd import given, parsers, then, when

from tests.bdd.steps.common_steps import (
    CASE_STATUS_ZH,
    client_of,
    create_case,
    csrf_headers,
    get_case,
    lifecycle,
    save_case,
    standard_document,
)


@given(parsers.parse('教师"{persona}"创建的草稿案例"{title}"已提交送审'))
def submitted_case(ctx, persona, title):
    create_case(ctx, persona, title, "已写好的内容")
    case_id = ctx["cases"][title]["id"]
    response = lifecycle(ctx, persona, case_id, "submit")
    assert response.status_code == 200, response.text
    ctx["memo"]["submitted_version_id"] = response.json()["version"]["id"]


@given(parsers.parse('教师的草稿案例"{title}"已提交且审核已开始'))
def reviewing_case(ctx, title):
    submitted_case(ctx, "教师", title)
    case_id = ctx["cases"][title]["id"]
    response = lifecycle(ctx, "管理员", case_id, "start")
    assert response.status_code == 200, response.text


@given(parsers.parse('教师的草稿案例"{title}"已发布'))
def published_case(ctx, title):
    submitted_case(ctx, "教师", title)
    case_id = ctx["cases"][title]["id"]
    started = lifecycle(ctx, "管理员", case_id, "start")
    assert started.status_code == 200
    approved = lifecycle(ctx, "管理员", case_id, "approve",
                         submittedVersionId=ctx["memo"]["submitted_version_id"])
    assert approved.status_code == 200, approved.text


@when(parsers.parse('教师提交"{title}"送审'))
def teacher_submits(ctx, title):
    case_id = ctx["cases"][title]["id"]
    ctx["memo"]["last_response"] = lifecycle(ctx, "教师", case_id, "submit")


@then(parsers.parse('提交成功且案例状态为"{status}"'))
def submitted_status(ctx, status):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 200, response.text
    assert response.json()["case"]["workflowStatus"] == CASE_STATUS_ZH[status]
    ctx["memo"]["submitted_version_id"] = response.json()["version"]["id"]


@then("案例正文锁定为只读")
def case_locked(ctx):
    case_id = ctx["memo"]["current_case_id"]
    case = get_case(ctx, case_id)
    assert case["workflowStatus"] != "draft"
    locked = save_case(ctx, "教师", case_id, title=case["title"],
                       document=standard_document("冻结期改动"))
    assert locked.status_code == 409, locked.text


@when("管理员开始审核并最终通过")
def admin_starts_and_approves(ctx):
    case_id = ctx["memo"]["current_case_id"]
    started = lifecycle(ctx, "管理员", case_id, "start")
    assert started.status_code == 200, started.text
    current = get_case(ctx, case_id)
    ctx["memo"]["last_response"] = lifecycle(
        ctx, "管理员", case_id, "approve",
        submittedVersionId=current["submittedVersionId"],
    )


@then(parsers.parse('案例状态为"{status}"且公开可见'))
def published_and_public(ctx, status):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 200, response.text
    case = response.json()["case"]
    assert case["workflowStatus"] == CASE_STATUS_ZH[status]
    assert case["publicationStatus"] == "public"
    public = client_of(ctx).get(f"/api/cases/{case['id']}/public")
    assert public.status_code == 200, public.text
    assert public.json()["id"] == case["id"]


@when(parsers.parse('教师撤回"{title}"'))
def teacher_withdraws(ctx, title):
    case_id = ctx["cases"][title]["id"]
    ctx["memo"]["last_response"] = lifecycle(ctx, "教师", case_id, "withdraw")


@then(parsers.parse('案例回到草稿状态且正文可继续编辑'))
def back_to_editable_draft(ctx):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 200, response.text
    case = response.json()["case"]
    assert case["workflowStatus"] == "draft"
    saved = save_case(ctx, "教师", case["id"], title=case["title"],
                      document=standard_document("撤回后的修改"))
    assert saved.status_code == 200, saved.text


@when(parsers.parse('管理员不带原因退回"{title}"'))
def admin_rejects_without_reason(ctx, title):
    case_id = ctx["cases"][title]["id"]
    case = get_case(ctx, case_id)
    ctx["memo"]["last_response"] = client_of(ctx).post(
        f"/api/cases/{case_id}/lifecycle", headers=csrf_headers(ctx, "管理员"),
        json={"command": "reject", "revision": case["revision"]},
    )


@then("校验失败并要求提供退回原因")
def validation_requires_reason(ctx):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 422, response.text
    message = str(response.json()["detail"])
    assert "reasonType" in message, message


@when(parsers.parse('管理员以"{reason}"退回"{title}"'))
def admin_rejects_with_reason(ctx, reason, title):
    case_id = ctx["cases"][title]["id"]
    current = get_case(ctx, case_id)
    ctx["memo"]["last_response"] = lifecycle(
        ctx, "管理员", case_id, "reject", reasonType=reason,
        submittedVersionId=current["submittedVersionId"],
    )


@when(parsers.parse('教师看到"{title}"的退回原因"{reason}"'))
def teacher_sees_return_reason(ctx, title, reason):
    case_id = ctx["cases"][title]["id"]
    response = client_of(ctx).get(
        "/api/cases?scope=mine", headers=csrf_headers(ctx, "教师")
    )
    assert response.status_code == 200, response.text
    card = next(row for row in response.json() if row["id"] == case_id)
    assert card["lastReview"]["action"] == "reject"
    assert card["lastReview"]["reasonType"] == reason


@when(parsers.parse('教师重新提交"{title}"'))
def teacher_resubmits(ctx, title):
    case_id = ctx["cases"][title]["id"]
    ctx["memo"]["last_response"] = lifecycle(ctx, "教师", case_id, "submit")


@then(parsers.parse('案例状态为"{status}"且历史反馈被清除'))
def resubmitted_feedback_cleared(ctx, status):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 200, response.text
    assert response.json()["case"]["workflowStatus"] == CASE_STATUS_ZH[status]
    mine = client_of(ctx).get(
        "/api/cases?scope=mine", headers=csrf_headers(ctx, "教师")
    ).json()
    card = next(row for row in mine if row["id"] == ctx["memo"]["current_case_id"])
    assert card["lastReview"] is None


@when(parsers.parse('教师尝试把"{title}"正文改为"{text}"'))
def teacher_edits_locked(ctx, title, text):
    case_id = ctx["cases"][title]["id"]
    ctx["memo"]["last_response"] = save_case(
        ctx, "教师", case_id, title=ctx["cases"][title]["title"],
        document=standard_document(text),
    )


@when(parsers.parse('管理员下线"{title}"'))
def admin_hides(ctx, title):
    case_id = ctx["cases"][title]["id"]
    ctx["memo"]["last_response"] = lifecycle(ctx, "管理员", case_id, "hide")


@when(parsers.parse('教师对"{title}"执行另起新稿'))
def teacher_reopens(ctx, title):
    case_id = ctx["cases"][title]["id"]
    ctx["memo"]["last_response"] = lifecycle(ctx, "教师", case_id, "reopen")


@then(parsers.parse('案例回到草稿状态且已发布版本历史仍被记录'))
def reopened_but_public_version_readable(ctx):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 200, response.text
    case = response.json()["case"]
    assert case["workflowStatus"] == CASE_STATUS_ZH["草稿"]
    # 下线后公开阅读端按 publicationStatus!=public 拒绝（404），旧发布版本仍在历史中
    public = client_of(ctx).get(f"/api/cases/{case['id']}/public")
    assert public.status_code == 404
    history = client_of(ctx).get(
        f"/api/cases/{case['id']}/history", headers=csrf_headers(ctx, "教师")
    )
    assert history.status_code == 200
    actions = [row["action"] for row in history.json().get("events", [])]
    assert "approve" in actions
