"""DOCX导出场景步骤。"""
from __future__ import annotations

import io

from docx import Document as read_docx
from pytest_bdd import given, parsers, then, when

from tests.bdd.steps.common_steps import client_of, create_case, csrf_headers


@given(parsers.parse('已有草稿案例"{title}"'))
def draft_case_exists(ctx, title):
    create_case(ctx, "教师", title, f"{title}的正文")


@when(parsers.parse('教师导出"{title}"为DOCX'))
def teacher_exports_docx(ctx, title):
    case_id = ctx["cases"][title]["id"]
    ctx["memo"]["last_response"] = client_of(ctx).get(
        f"/api/cases/{case_id}/export.docx", headers=csrf_headers(ctx, "教师")
    )
    ctx["memo"]["export_case_title"] = ctx["cases"][title]["title"]


@then("导出件是合法Word文件且包含标题与正文")
def docx_is_valid_and_complete(ctx):

    response = ctx["memo"]["last_response"]
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )
    document = read_docx(io.BytesIO(response.content))
    full_text = "\n".join(p.text for p in document.paragraphs)
    title = ctx["memo"]["export_case_title"]
    assert title in full_text or any(title in p.text for p in document.paragraphs)
    assert "导出的正文内容" in full_text
    assert len(document.inline_shapes) >= 1  # 校名 Logo 嵌入


@when(parsers.parse('未登录访客导出"{title}"的DOCX'))
def anonymous_exports_docx(ctx, title):
    case_id = ctx["cases"][title]["id"]
    ctx["client"].cookies.clear()
    ctx["memo"]["last_response"] = client_of(ctx).get(
        f"/api/cases/{case_id}/export.docx"
    )
