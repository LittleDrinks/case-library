"""账号与权限场景步骤。"""
from __future__ import annotations

from pytest_bdd import given, parsers, then, when

from tests.bdd.steps.common_steps import client_of, get_case, save_case, standard_document


@then("会话中显示教师身份与csrf令牌")
def session_shows_teacher(ctx):
    session = client_of(ctx).get("/api/auth/session")
    assert session.status_code == 200
    body = session.json()
    assert body["user"]["role"] == "user"
    assert body["csrfToken"]


@when(parsers.parse('教师"小张"用错误密码登录'))
def wrong_password_login(ctx):
    response = client_of(ctx).post(
        "/api/auth/login", json={"username": "user", "password": "wrong-password"}
    )
    ctx["memo"]["wrong_password_response"] = response
    ctx["memo"]["last_response"] = response


@then("登录被拒绝且不泄露账号是否存在")
def login_rejected_generic(ctx):
    response = ctx["memo"]["wrong_password_response"]
    assert response.status_code == 401
    assert response.json() == {"detail": "用户名或密码错误"}
    missing = client_of(ctx).post(
        "/api/auth/login",
        json={"username": "missing-user", "password": "wrong-password"},
    )
    assert (missing.status_code, missing.json()) == (
        response.status_code, response.json()
    )

@when(parsers.parse('匿名访客请求案例"{case_id}"'))
def anonymous_reads_case(ctx, case_id):
    ctx["memo"]["last_response"] = client_of(ctx).get(f"/api/cases/{case_id}")


@when(parsers.parse('教师不带CSRF令牌创建案例"{title}"'))
def create_case_without_csrf(ctx, title):
    ctx["memo"]["last_response"] = client_of(ctx).post(
        "/api/cases",
        json={"title": title, "document": {"type": "doc", "content": []}},
    )


@when(parsers.parse('管理员尝试把"{title}"正文改为"{text}"'))
def admin_edits_author_draft(ctx, title, text):

    case = get_case(ctx, ctx["cases"][title]["id"])
    ctx["memo"]["last_response"] = save_case(
        ctx, "管理员", case["id"], title=case["title"],
        document=standard_document(text),
    )


@given(parsers.parse('名册账号"{username}"首次登录'))
def roster_account_first_login(ctx, username):
    response = client_of(ctx).post(
        "/api/auth/login",
        json={"username": username, "password": f"Demo-{username}-2026!"},
    )
    assert response.status_code == 200, response.text
    ctx["sessions"]["名册账号"] = response.json()
    ctx["memo"]["roster_username"] = username


@when("该账号尝试创建案例\"改密前案例\"")
def roster_creates_case(ctx):
    session = ctx["sessions"]["名册账号"]
    ctx["memo"]["last_response"] = client_of(ctx).post(
        "/api/cases",
        headers={"X-CSRF-Token": session["csrfToken"]},
        json={"title": "改密前案例",
              "document": {"type": "doc", "content": []}},
    )


@then("提示要求先修改密码")
def rejected_for_password_change(ctx):
    response = ctx["memo"]["last_response"]
    assert response.json()["detail"] == "请先修改初始密码", response.text


@when(parsers.parse('停用账号"{username}"尝试登录'))
def disabled_account_login(ctx, username):
    ctx["memo"]["last_response"] = client_of(ctx).post(
        "/api/auth/login",
        json={"username": username, "password": f"Demo-{username}-2026!"},
    )


@then("停用账号按无效凭据处理")
def disabled_login_rejected(ctx):
    response = ctx["memo"]["last_response"]
    assert response.status_code == 401
    assert response.json()["detail"] == "用户名或密码错误"


@given(parsers.parse('另一标签页已把"{title}"正文改为"{text}"'))
def another_tab_saves(ctx, title, text):

    case = get_case(ctx, ctx["cases"][title]["id"])
    response = save_case(ctx, "教师", case["id"], title=case["title"],
                         document=standard_document(text))
    assert response.status_code == 200, response.text
    ctx["memo"]["newer_revision"] = response.json()["revision"]


@when(parsers.parse('教师用旧修订号把"{title}"正文改为"{text}"'))
def stale_save(ctx, title, text):
    from app.modules.agent import prosemirror

    case = get_case(ctx, ctx["cases"][title]["id"])
    stale_revision = case["revision"] - 1
    document = standard_document(text)
    _, steps = prosemirror.replace_document(case["document"], document)
    ctx["memo"]["last_response"] = ctx["client"].patch(
        f"/api/cases/{case['id']}",
        headers={"X-CSRF-Token": ctx["sessions"]["教师"]["csrfToken"]},
        json={"revision": stale_revision, "title": case["title"],
              "document": document, "steps": steps},
    )


@then("冲突响应带回当前修订号")
def conflict_carries_revision(ctx):
    response = ctx["memo"]["last_response"]
    body = response.json()
    assert body["currentRevision"] == ctx["memo"]["newer_revision"], body
