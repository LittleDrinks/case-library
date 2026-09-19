"""来源引用场景步骤。"""
from __future__ import annotations

from pytest_bdd import given, parsers, then, when

from app.modules.agent import prosemirror
from tests.bdd.steps.common_steps import (
    client_of,
    create_case,
    csrf_headers,
    get_case,
)


def _mount(ctx, source_case_id: str):
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    return client_of(ctx).post(
        f"/api/cases/{case['id']}/case-sources",
        headers=csrf_headers(ctx, "教师"),
        json={"sourceCaseId": source_case_id, "revision": case["revision"]},
    )


def _sources(ctx):
    case_id = ctx["memo"]["current_case_id"]
    response = client_of(ctx).get(
        f"/api/cases/{case_id}/case-sources", headers=csrf_headers(ctx, "教师")
    )
    assert response.status_code == 200, response.text
    return response.json()


@when(parsers.parse('教师把已发布案例"{source}"挂载为来源'))
def teacher_mounts_source(ctx, source):
    ctx["memo"]["last_response"] = _mount(ctx, source)


@then(parsers.parse('挂载成功且来源列表包含"{source}"的已发布版本'))
def mounted_with_version(ctx, source):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 201, response.text
    published = client_of(ctx).get(f"/api/cases/{source}/public").json()
    assert response.json()["versionId"] == published["publishedVersionId"]
    assert any(row["caseId"] == source for row in _sources(ctx))


@given(parsers.parse('"{title}"已挂载来源"{source}"'))
def mounted_source(ctx, title, source):
    if title not in ctx["cases"]:
        create_case(ctx, "教师", title, f"{title}的正文")
    ctx["memo"]["current_case_id"] = ctx["cases"][title]["id"]
    response = _mount(ctx, source)
    assert response.status_code == 201, response.text
    ctx["memo"].setdefault("mounted", {})[source] = response.json()


@given(parsers.parse('"{title}"已挂载"{source}"并在正文引用'))
def mounted_and_cited(ctx, title, source):
    mounted_source(ctx, title, source)
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    source_row = ctx["memo"]["mounted"][source]
    document = {"type": "doc", "content": [{
        "type": "paragraph",
        "content": [{"type": "text", "text": "依据",
                     "marks": [{"type": "citation",
                                "attrs": {"sourceType": "case",
                                          "sourceId": source_row["id"]}}]}],
    }]}
    _, steps = prosemirror.replace_document(case["document"], document)
    saved = client_of(ctx).patch(
        f"/api/cases/{case['id']}", headers=csrf_headers(ctx, "教师"),
        json={"revision": case["revision"], "title": case["title"],
              "document": document, "steps": steps},
    )
    assert saved.status_code == 200, saved.text


@given(parsers.parse('"{title}"已挂载"{source}"但正文未引用'))
def mounted_without_citation(ctx, title, source):
    mounted_source(ctx, title, source)


@when(parsers.parse('教师再次把"{source}"挂载为来源'))
def teacher_remounts(ctx, source):
    ctx["memo"]["last_response"] = _mount(ctx, source)


@when(parsers.parse('教师尝试删除来源"{source}"'))
def teacher_deletes_source(ctx, source):
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    source_row = ctx["memo"]["mounted"][source]
    ctx["memo"]["last_response"] = client_of(ctx).delete(
        f"/api/cases/{case['id']}/case-sources/{source_row['id']}",
        params={"revision": case["revision"]},
        headers=csrf_headers(ctx, "教师"),
    )


@when(parsers.parse('教师删除来源"{source}"'))
def teacher_removes_source(ctx, source):
    teacher_deletes_source(ctx, source)
    response = ctx["memo"]["last_response"]
    assert response.status_code == 204, response.text


@then(parsers.parse('来源列表不再包含"{source}"'))
def sources_exclude(ctx, source):
    assert all(row["caseId"] != source for row in _sources(ctx))


@when(parsers.parse('管理员下线案例"{source}"'))
def admin_hides_source_case(ctx, source):
    from tests.bdd.steps.common_steps import lifecycle

    response = lifecycle(ctx, "管理员", source, "hide")
    assert response.status_code == 200, response.text


@then(parsers.parse('引用来源条目标记为不可读'))
def source_entry_locked(ctx):
    rows = _sources(ctx)
    assert rows, rows
    assert all(row["contentAvailable"] is False for row in rows), rows
