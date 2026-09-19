"""版本隔离与恢复场景步骤。"""
from __future__ import annotations

from pytest_bdd import given, parsers, then, when

from tests.bdd.steps.common_steps import (
    client_of,
    create_case,
    csrf_headers,
    get_case,
    lifecycle,
    save_case,
    standard_document,
)


def document_text(document: dict) -> str:
    """正文段落文本（不含小节标题）。"""
    paragraphs = []
    for block in document.get("content", []):
        if block.get("type") != "paragraph":
            continue
        paragraphs.append(
            "".join(c.get("text", "") for c in block.get("content") or [])
        )
    return "\n".join(part for part in paragraphs if part)


@given(parsers.parse('教师创建草稿案例"{title}"，正文包含"{text}"'))
def create_draft_baseline(ctx, title, text):
    create_case(ctx, "教师", title, text)


@when(parsers.parse('教师把"{title}"正文改为"{text}"'))
def teacher_edits(ctx, title, text):
    case_id = ctx["cases"][title]["id"]
    ctx["memo"]["last_response"] = save_case(
        ctx, "教师", case_id, title=ctx["cases"][title]["title"],
        document=standard_document(text),
    )
    assert ctx["memo"]["last_response"].status_code == 200, \
        ctx["memo"]["last_response"].text


@when(parsers.parse('教师以"{name}"命名当前版本'))
def teacher_freezes_version(ctx, name):
    case_id = ctx["memo"]["current_case_id"]
    case = get_case(ctx, case_id)
    ctx["memo"]["last_response"] = client_of(ctx).post(
        f"/api/cases/{case_id}/versions", headers=csrf_headers(ctx, "教师"),
        json={"title": name, "revision": case["revision"]},
    )
    assert ctx["memo"]["last_response"].status_code == 200, \
        ctx["memo"]["last_response"].text
    ctx["cases"].setdefault("_versions", {})[name] = \
        ctx["memo"]["last_response"].json()


def _history(ctx, case_id: str) -> dict:
    response = client_of(ctx).get(
        f"/api/cases/{case_id}/history", headers=csrf_headers(ctx, "教师")
    )
    assert response.status_code == 200, response.text
    return response.json()


@then(parsers.parse('版本历史中"{name}"保存的正文是"{text}"'))
def frozen_version_keeps_content(ctx, name, text):
    history = _history(ctx, ctx["memo"]["current_case_id"])
    version = next(row for row in history["versions"] if row["title"] == name)
    assert document_text(version["document"]) == text


@then(parsers.parse('当前工作稿正文是"{text}"'))
def current_document_is(ctx, text):
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    assert document_text(case["document"]) == text


@given(parsers.parse('教师的"{title}"存在历史版本"{name}"且当前稿已改动'))
def case_with_history_and_changed_draft(ctx, title, name):
    create_case(ctx, "教师", title, f"{title}的初稿")
    case_id = ctx["memo"]["current_case_id"]
    frozen = client_of(ctx).post(
        f"/api/cases/{case_id}/versions", headers=csrf_headers(ctx, "教师"),
        json={"title": name, "revision": get_case(ctx, case_id)["revision"]},
    )
    assert frozen.status_code == 200, frozen.text
    ctx["cases"].setdefault("_versions", {})[name] = frozen.json()
    changed = save_case(ctx, "教师", case_id,
                        document=standard_document(f"{title}的最新改动"))
    assert changed.status_code == 200, changed.text


@when(parsers.parse('教师恢复"{name}"'))
def teacher_restores(ctx, name):
    case_id = ctx["memo"]["current_case_id"]
    version = ctx["cases"]["_versions"][name]
    ctx["memo"]["before_restore_document"] = get_case(ctx, case_id)["document"]
    ctx["memo"]["before_restore_ids"] = {row["id"] for row in _history(ctx, case_id)["versions"]}
    ctx["memo"]["last_response"] = lifecycle(
        ctx, "教师", case_id, "overwrite", targetId=version["id"]
    )


@then(parsers.parse('当前工作稿正文是历史版本"{name}"的内容'))
def current_matches_restored(ctx, name):
    version = ctx["cases"]["_versions"][name]
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    assert case["document"] == version["document"]


@then(parsers.parse('版本历史新增恢复记录且旧版本仍在'))
def restore_record_appended(ctx):
    history = _history(ctx, ctx["memo"]["current_case_id"])
    kinds = [row["kind"] for row in history["versions"]]
    assert kinds[-1] == "restore"
    added = [row for row in history["versions"]
             if row["id"] not in ctx["memo"]["before_restore_ids"]]
    assert [row["kind"] for row in added] == ["manual", "restore"]
    assert added[0]["title"] == "恢复前的当前稿"
    assert added[0]["document"] == ctx["memo"]["before_restore_document"]
    frozen = ctx["cases"]["_versions"]
    ids = [row["id"] for row in history["versions"]]
    for version in frozen.values():
        assert version["id"] in ids


@given(parsers.parse('教师的"取消恢复案例"存在历史版本"检查点乙"且当前稿已改动'))
def cancel_restore_fixture(ctx):
    case_with_history_and_changed_draft(ctx, "取消恢复案例", "检查点乙")


@when(parsers.parse('教师以过期的修订号尝试恢复"{name}"'))
def restore_with_stale_revision(ctx, name):
    case_id = ctx["memo"]["current_case_id"]
    case = get_case(ctx, case_id)
    version = ctx["cases"]["_versions"][name]
    ctx["memo"]["last_response"] = client_of(ctx).post(
        f"/api/cases/{case_id}/lifecycle", headers=csrf_headers(ctx, "教师"),
        json={"command": "overwrite", "revision": case["revision"] + 5,
              "targetId": version["id"]},
    )


@then(parsers.parse('当前工作稿正文保持"{title}"的最新改动'))
def draft_unchanged_after_failed_restore(ctx, title):
    case = get_case(ctx, ctx["cases"][title]["id"])
    assert document_text(case["document"]) == f"{title}的最新改动"


@then("版本历史没有新增恢复记录")
def no_restore_record(ctx):
    history = _history(ctx, ctx["memo"]["current_case_id"])
    assert all(row["kind"] != "restore" for row in history["versions"])


@given(parsers.parse('教师的"{title}"存在手动命名版本"{name}"'))
def case_with_manual_version(ctx, title, name):
    create_case(ctx, "教师", title, f"{title}的手动版本前内容")
    case_id = ctx["memo"]["current_case_id"]
    frozen = client_of(ctx).post(
        f"/api/cases/{case_id}/versions", headers=csrf_headers(ctx, "教师"),
        json={"title": name, "revision": get_case(ctx, case_id)["revision"]},
    )
    assert frozen.status_code == 200, frozen.text
    ctx["cases"].setdefault("_versions", {})[name] = frozen.json()


@when(parsers.parse('教师删除版本"{name}"'))
def teacher_deletes_version(ctx, name):
    case_id = ctx["memo"]["current_case_id"]
    version = ctx["cases"]["_versions"][name]
    ctx["memo"]["last_response"] = client_of(ctx).delete(
        f"/api/cases/{case_id}/versions/{version['id']}",
        headers=csrf_headers(ctx, "教师"),
    )


@then(parsers.parse('版本历史不再包含"{name}"'))
def history_excludes_version(ctx, name):
    history = _history(ctx, ctx["memo"]["current_case_id"])
    assert all(row["title"] != name for row in history["versions"])


@then("当前工作稿正文不变")
def current_document_unchanged(ctx):
    case = get_case(ctx, ctx["memo"]["current_case_id"])
    assert document_text(case["document"]) == \
        f"{case['title']}的手动版本前内容"


@given(parsers.parse('教师的"{title}"已提交送审且审核中'))
def case_is_reviewing(ctx, title):
    create_case(ctx, "教师", title, f"{title}的送审正文")
    case_id = ctx["memo"]["current_case_id"]
    submitted = lifecycle(ctx, "教师", case_id, "submit")
    assert submitted.status_code == 200
    ctx["memo"]["submitted_version_id"] = submitted.json()["version"]["id"]
    started = lifecycle(ctx, "管理员", case_id, "start")
    assert started.status_code == 200


@when("教师删除该送审版本")
def teacher_deletes_submitted_version(ctx):
    case_id = ctx["memo"]["current_case_id"]
    ctx["memo"]["last_response"] = client_of(ctx).delete(
        f"/api/cases/{case_id}/versions/{ctx['memo']['submitted_version_id']}",
        headers=csrf_headers(ctx, "教师"),
    )
