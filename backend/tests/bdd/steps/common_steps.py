"""业务步骤公共层：登录、案例创建/保存、生命周期与断言辅助。

步骤驱动真实应用 HTTP（TestClient），断言用户可观察响应，不读内部存储。
"""
from __future__ import annotations

import hashlib
import io

from pytest_bdd import given, parsers, then, when

PERSONA_ACCOUNTS = {"管理员": ("admin", "admin123"), "教师": ("user", "user123")}

# 与工作台界面文案一致的状态映射（WorkbenchView.vue caseStatusLabel）。
CASE_STATUS_ZH = {"草稿": "draft", "待审": "pending", "审核中": "reviewing", "已发布": "published"}


def client_of(ctx):
    return ctx["client"]


def login_as(ctx, persona: str) -> dict:
    """按业务角色登录演示账号。每个角色独立会话（显式 Cookie 头，不依赖共享 jar）。"""
    sessions = ctx["sessions"]
    if persona not in sessions:
        username, password = PERSONA_ACCOUNTS[persona]
        response = client_of(ctx).post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        assert response.status_code == 200, response.text
        session = response.json()
        set_cookie = response.headers["set-cookie"]
        session["cookie"] = set_cookie.split(";", 1)[0]
        sessions[persona] = session
    return sessions[persona]


def auth_headers(ctx, persona: str) -> dict:
    """带该角色会话 Cookie 与 CSRF 头，支持多角色在同一场景内交错操作。"""
    session = login_as(ctx, persona)
    return {"X-CSRF-Token": session["csrfToken"], "Cookie": session["cookie"]}


def csrf_headers(ctx, persona: str) -> dict:
    return auth_headers(ctx, persona)


def anonymous_cookies_clear(ctx) -> None:
    ctx["client"].cookies.clear()


def get_case(ctx, case_id: str) -> dict:
    response = client_of(ctx).get(f"/api/cases/{case_id}")
    assert response.status_code == 200, response.text
    return response.json()


def standard_document(*paragraphs: str) -> dict:
    content = [{
        "type": "heading", "attrs": {"level": 1},
        "content": [{"type": "text", "text": "一、教学说明"}],
    }]
    content.extend(
        {"type": "paragraph", "content": [{"type": "text", "text": text}]}
        for text in paragraphs
    )
    return {"type": "doc", "content": content}


def create_case(ctx, persona: str, title: str, *paragraphs: str) -> dict:
    response = client_of(ctx).post(
        "/api/cases",
        headers=csrf_headers(ctx, persona),
        json={"title": title, "document": standard_document(*paragraphs)},
    )
    assert response.status_code == 200, response.text
    case = response.json()
    ctx["cases"][title] = case
    ctx["memo"]["current_case_id"] = case["id"]
    return case


def lifecycle(ctx, persona: str, case_id: str, command: str, **extra) -> object:
    case = get_case(ctx, case_id)
    body = {"command": command, "revision": case["revision"], **extra}
    return client_of(ctx).post(
        f"/api/cases/{case_id}/lifecycle", headers=csrf_headers(ctx, persona), json=body
    )


def save_case(ctx, persona: str, case_id: str, **body) -> object:
    case = get_case(ctx, case_id)
    if body.get("document") is not None and body.get("steps") is None:
        from app.modules.agent import prosemirror

        _, steps = prosemirror.replace_document(case["document"], body["document"])
        body["steps"] = steps
    payload = {"revision": case["revision"], **body}
    return client_of(ctx).patch(
        f"/api/cases/{case_id}", headers=csrf_headers(ctx, persona), json=payload
    )


def upload_attachment(ctx, persona: str, case_id: str, name: str, content: bytes,
                      access: str = "public") -> object:
    case = get_case(ctx, case_id)
    return client_of(ctx).post(
        f"/api/cases/{case_id}/attachments",
        headers=csrf_headers(ctx, persona),
        files={"file": (name, io.BytesIO(content), "text/plain")},
        data={"accessLevel": access, "revision": str(case["revision"])},
    )


def utf16_size(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def paragraph_offset(*prior_paragraphs: str) -> int:
    """标准文档正文第 N 段起点：标题 UTF-16 长度 + 标题节点边界 3 + 前置段落。"""
    heading = "一、教学说明"
    return (
        utf16_size(heading) + 3
        + sum(utf16_size(text) + 2 for text in prior_paragraphs)
    )


def anchor_payload(case: dict, section: str, quote: str, prior: tuple[str, ...] = (),
                   content: str = "请补充教学依据。") -> dict:
    start = paragraph_offset(*prior)
    return {
        "from": start, "to": start + utf16_size(quote), "quote": quote,
        "section": section, "quoteHash": hashlib.sha256(quote.encode()).hexdigest(),
        "revision": case["revision"], "content": content, "source": "manual",
    }


def create_annotation(ctx, persona: str, case_id: str, payload: dict) -> object:
    return client_of(ctx).post(
        f"/api/cases/{case_id}/annotations", headers=csrf_headers(ctx, persona),
        json=payload,
    )


def submit_case(ctx, persona: str, case_id: str) -> object:
    return lifecycle(ctx, persona, case_id, "submit")


def case_by_title(ctx, title: str) -> dict:
    if title in ctx["cases"]:
        return get_case(ctx, ctx["cases"][title]["id"])
    return get_case(ctx, ctx["memo"]["current_case_id"])


# ---------- Given ----------

@given(parsers.parse('已登录的{persona}'))
def logged_in(ctx, persona):
    login_as(ctx, persona)


@given(parsers.parse('{persona}创建草稿案例"{title}"，正文包含"{text}"'))
def author_creates_draft(ctx, persona, title, text):
    create_case(ctx, persona, title, text)


# ---------- When ----------

@when(parsers.parse('{persona}把"{title}"正文改为"{text}"并保存'))
def save_document_text(ctx, persona, title, text):
    case = case_by_title(ctx, title)
    ctx["memo"]["last_response"] = save_case(
        ctx, persona, case["id"], title=case["title"],
        document=standard_document(text),
    )


# ---------- Then ----------

@then("操作成功")
def operation_succeeds(ctx):
    response = ctx["memo"]["last_response"]
    assert response.status_code < 400, f"{response.status_code}: {response.text}"


@then(parsers.parse('操作被拒绝，提示"{detail}"'))
def operation_rejected_with(ctx, detail):
    response = ctx["memo"]["last_response"]
    assert response.status_code >= 400, f"预期拒绝，实际成功: {response.text}"
    assert response.json()["detail"] == detail, response.text


@then(parsers.parse('响应状态码为{code:d}'))
def response_status_is(ctx, code):
    assert ctx["memo"]["last_response"].status_code == code, ctx["memo"]["last_response"].text
