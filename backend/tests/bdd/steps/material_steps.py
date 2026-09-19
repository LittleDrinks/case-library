"""资料导入与审核场景步骤。"""
from __future__ import annotations

import io

from pytest_bdd import given, parsers, then, when

from tests.bdd.steps.common_steps import client_of, csrf_headers, login_as


def _import_files(ctx, persona: str, files: list[tuple], access="public") -> object:
    return client_of(ctx).post(
        "/api/admin/material-imports",
        headers=csrf_headers(ctx, persona),
        data={"accessLevel": access},
        files=[("files", (name, io.BytesIO(content), "text/plain"))
               for name, content in files],
    )


@when(parsers.parse('管理员导入资料文件"{name1}"与"{name2}"'))
def admin_imports_two(ctx, name1, name2):
    ctx["memo"]["last_response"] = _import_files(
        ctx, "管理员",
        [(name1, f"# {name1} 的内容".encode()), (name2, f"{name2} 内容".encode())],
    )


@then("导入任务成功且生成两份候选")
def import_succeeded_two_candidates(ctx):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["status"] == "succeeded"
    assert [item["status"] for item in job["items"]] == ["candidate", "candidate"]


@given(parsers.parse('管理员已导入内容为"{content}"的资料'))
def imported_once(ctx, content):
    login_as(ctx, "管理员")
    response = _import_files(ctx, "管理员", [("原始资料.md", content.encode())])
    assert response.status_code == 201, response.text
    ctx["memo"]["first_import_item"] = response.json()["items"][0]


ACCESS_LEVEL_ZH = {"公开": "public", "校内": "campus", "私密": "private"}


@given(parsers.parse('管理员已以"{access}"级别导入内容为"{content}"的资料并批准'))
def imported_campus_approved(ctx, access, content):
    login_as(ctx, "管理员")
    job = _import_files(ctx, "管理员",
                        [(f"校内资料-{content[:6]}.md", content.encode("utf-8"))],
                        access=ACCESS_LEVEL_ZH[access]).json()
    item = job["items"][0]
    assert item["status"] == "candidate", item
    response = client_of(ctx).post(
        f"/api/admin/material-candidates/{item['candidateId']}/decision",
        headers=csrf_headers(ctx, "管理员"),
        json={"decision": "approve", "title": f"{content}标题"},
    )
    assert response.status_code == 200, response.text
    ctx["memo"]["approved_material_id"] = response.json()["materialId"]


@when(parsers.parse('管理员以新文件名再次导入相同内容'))
def import_duplicate(ctx):
    ctx["memo"]["last_response"] = _import_files(
        ctx, "管理员", [("再次上传.md", "独家教学心得".encode())]
    )


@then(parsers.parse('新条目被标记为"{status}"并指向原候选'))
def duplicate_marked(ctx, status):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 201, response.text
    item = response.json()["items"][0]
    assert item["status"] == {"重复": "duplicate"}[status]
    assert item["duplicateOf"] == ctx["memo"]["first_import_item"]["candidateId"]


@when(parsers.parse('教师尝试导入资料文件"{name}"'))
def teacher_imports(ctx, name):
    database = client_of(ctx).app.state.database
    collections = ("material_import_jobs", "material_import_items", "material_candidates")
    before = {name: list(database[name].find({}).sort("id", 1)) for name in collections}
    ctx["memo"]["teacher_import_response"] = client_of(ctx).post(
        "/api/admin/material-imports",
        headers=csrf_headers(ctx, "教师"),
        data={"accessLevel": "public"},
        files=[("files", (name, io.BytesIO(b"import content"), "text/plain"))],
    )
    ctx["memo"]["last_response"] = ctx["memo"]["teacher_import_response"]
    after = {name: list(database[name].find({}).sort("id", 1)) for name in collections}
    assert after == before



@when("教师尝试审核该资料候选")
def teacher_reviews_candidate(ctx):
    imported = _import_files(
        ctx, "管理员", [("待越权审核.txt", "待越权审核内容".encode("utf-8"))]
    )
    item = imported.json()["items"][0]
    ctx["memo"]["review_candidate_id"] = item["candidateId"]
    ctx["memo"]["review_candidate_before"] = client_of(ctx).app.state.database.material_candidates.find_one(
        {"id": item["candidateId"]}, {"_id": 0}
    )
    ctx["memo"]["last_response"] = client_of(ctx).post(
        f"/api/admin/material-candidates/{item['candidateId']}/decision",
        headers=csrf_headers(ctx, "教师"),
        json={"decision": "approve", "title": "不应批准"},
    )


@then("导入与审核均被拒绝且候选未改变")
def material_import_and_review_denied(ctx):
    import_response = ctx["memo"]["teacher_import_response"]
    assert import_response.status_code == 403, import_response.text
    review_response = ctx["memo"]["last_response"]
    assert review_response.status_code == 403, review_response.text
    candidate = client_of(ctx).app.state.database.material_candidates.find_one(
        {"id": ctx["memo"]["review_candidate_id"]}, {"_id": 0}
    )
    assert candidate == ctx["memo"]["review_candidate_before"]

@when(parsers.parse('管理员以标题"{title}"批准该候选'))
def admin_approves_candidate(ctx, title):
    item = ctx["memo"]["first_import_item"]
    ctx["memo"]["last_response"] = client_of(ctx).post(
        f"/api/admin/material-candidates/{item['candidateId']}/decision",
        headers=csrf_headers(ctx, "管理员"),
        json={"decision": "approve", "title": title},
    )
    assert ctx["memo"]["last_response"].status_code == 200, \
        ctx["memo"]["last_response"].text
    ctx["memo"]["approved_material_id"] = ctx["memo"]["last_response"].json()["materialId"]


@then("该素材正文可被登录用户读取")
def approved_material_readable(ctx):
    material_id = ctx["memo"]["approved_material_id"]
    response = client_of(ctx).get(
        f"/api/materials/{material_id}/content", headers=csrf_headers(ctx, "教师")
    )
    assert response.status_code == 200, response.text


@when(parsers.parse("未登录访客读取该素材正文"))
def anonymous_reads_material(ctx):
    material_id = ctx["memo"]["approved_material_id"]
    ctx["client"].cookies.clear()
    ctx["memo"]["last_response"] = client_of(ctx).get(
        f"/api/materials/{material_id}/content"
    )
