"""标签与Skill平台场景步骤。"""
from __future__ import annotations

from pytest_bdd import given, parsers, then, when

from tests.skill_packages import SKILL_DIR, build_package

from tests.bdd.steps.common_steps import (
    client_of,
    csrf_headers,
    get_case,
    lifecycle,
)


@when(parsers.parse('教师保存标签"{tag1}"与"{tag2}"'))
def teacher_saves_tags(ctx, tag1, tag2):
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    ctx["memo"]["requested_tags"] = [tag1, tag2]
    ctx["memo"]["last_response"] = client_of(ctx).patch(
        f"/api/cases/{case['id']}", headers=csrf_headers(ctx, "教师"),
        json={"revision": case["revision"], "tagIds": [tag1, tag2]},
    )
    assert ctx["memo"]["last_response"].status_code == 200, \
        ctx["memo"]["last_response"].text


@then("案例标签去重后为两个不同的种子标签")
def tags_deduped(ctx):
    tag1, tag2 = ctx["memo"]["requested_tags"]
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    assert case["tagIds"] == [tag1, tag2] and tag1 != tag2


@given(parsers.parse('管理员已建必填组"{group}"含标签"{tag_name}"'))
def required_group_exists(ctx, group, tag_name):
    admin = client_of(ctx).post(
        "/api/tag-groups", headers=csrf_headers(ctx, "管理员"),
        json={"name": group, "requiredForSubmission": True},
    )
    assert admin.status_code == 201, admin.text
    tag = client_of(ctx).post(
        f"/api/tag-groups/{admin.json()['id']}/tags",
        headers=csrf_headers(ctx, "管理员"),
        json={"name": tag_name},
    )
    assert tag.status_code == 201, tag.text
    ctx["memo"]["required_tag_id"] = tag.json()["id"]


@then(parsers.parse('提交被拦截并提示缺少必填组'))
def submit_blocked_by_group(ctx):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 422, response.text
    assert "投稿必填组" in response.json()["detail"]


@when("教师补选必填组标签并再次提交")
def teacher_resubmits_with_tag(ctx):
    case_id = ctx["memo"]["current_case_id"]
    case = get_case(ctx, case_id)
    saved = client_of(ctx).patch(
        f"/api/cases/{case_id}", headers=csrf_headers(ctx, "教师"),
        json={"revision": case["revision"],
              "tagIds": [ctx["memo"]["required_tag_id"]]},
    )
    assert saved.status_code == 200, saved.text
    ctx["memo"]["last_response"] = lifecycle(ctx, "教师", case_id, "submit")


# ---------- Skill ----------

def _upload_skill(ctx, persona: str) -> object:
    return client_of(ctx).post(
        "/api/admin/skills/packages", headers=csrf_headers(ctx, persona),
        files={"file": ("思政案例生成Skill包_v2.1.zip", build_package(),
                        "application/zip")},
    )


@when("管理员上传Skill压缩包")
def admin_uploads_skill(ctx):
    ctx["memo"]["last_response"] = _upload_skill(ctx, "管理员")
    assert ctx["memo"]["last_response"].status_code == 201, \
        ctx["memo"]["last_response"].text
    payload = ctx["memo"]["last_response"].json()
    ctx["memo"]["skill"] = {"id": payload["skill"]["id"],
                            "versionId": payload["version"]["id"]}


@when("管理员发布该Skill版本")
def admin_publishes_skill(ctx):
    skill = ctx["memo"]["skill"]
    ctx["memo"]["last_response"] = client_of(ctx).post(
        f"/api/admin/skills/{skill['id']}/publish",
        headers=csrf_headers(ctx, "管理员"),
        json={"versionId": skill["versionId"]},
    )
    assert ctx["memo"]["last_response"].status_code == 200, \
        ctx["memo"]["last_response"].text


@then(parsers.parse("教师端目录可见该Skill并可读取SKILL.md内容"))
def teacher_reads_skill(ctx):
    skill = ctx["memo"]["skill"]
    catalog = client_of(ctx).get("/api/skills", headers=csrf_headers(ctx, "教师")).json()
    assert any(row["id"] == skill["id"] for row in catalog), catalog
    content = client_of(ctx).get(
        f"/api/skills/{skill['id']}/content", headers=csrf_headers(ctx, "教师")
    ).json()
    assert content["path"] == f"{SKILL_DIR}/SKILL.md"
    assert "习近平文化思想课程思政案例生成技能" in content["content"]


@when("教师上传Skill压缩包")
def teacher_uploads_skill(ctx):
    ctx["memo"]["last_response"] = _upload_skill(ctx, "教师")
