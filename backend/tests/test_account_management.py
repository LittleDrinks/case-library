from __future__ import annotations

import secrets
import uuid

from fastapi.testclient import TestClient


def _password() -> str:
    return f"Issue357-{secrets.token_hex(16)}!a"


def _register(client: TestClient, username: str) -> tuple[dict, str]:
    password = _password()
    response = client.post(
        "/api/auth/register", json={"username": username, "password": password}
    )
    if response.status_code != 201:
        raise AssertionError("合成账号注册失败")
    return response.json(), password


def _make_admin(client: TestClient) -> tuple[str, str]:
    username = f"issue357-admin-{uuid.uuid4().hex}"
    account, password = _register(client, username)
    client.app.state.database.users.update_one(
        {"id": account["id"]}, {"$set": {"role": "admin"}}
    )
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    if response.status_code != 200:
        raise AssertionError("合成管理员登录失败")
    return username, response.json()["csrfToken"]


def test_admin_can_search_accounts_without_private_or_credential_fields(
    client: TestClient,
) -> None:
    _make_admin(client)
    username = f"issue357-search-{uuid.uuid4().hex}"
    account, password = _register(client, username)
    client.app.state.database.users.update_one(
        {"id": account["id"]},
        {
            "$set": {
                "campus_verified": True,
                "campus_identity": {"student_number": "synthetic-identity"},
                "private_profile": {"note": "synthetic-private-profile"},
            }
        },
    )

    response = client.get("/api/admin/accounts", params={"q": "ISSUE357-SEARCH"})

    assert response.status_code == 200
    accounts = response.json()
    assert accounts["total"] == 1
    assert len(accounts["items"]) == 1
    assert set(accounts["items"][0]) == {
        "id",
        "username",
        "role",
        "mustChangePassword",
    }
    assert accounts["items"][0]["id"] == account["id"]
    assert accounts["items"][0]["username"] == username
    assert accounts["items"][0]["role"] == "user"
    assert accounts["items"][0]["mustChangePassword"] is False
    serialized = response.text
    for secret in (password, "synthetic-identity", "synthetic-private-profile"):
        if secret in serialized:
            raise AssertionError("账号搜索响应包含凭据或非管理资料")
    if "password_hash" in serialized or "campusVerified" in serialized:
        raise AssertionError("账号搜索响应包含禁止字段")


def test_admin_opened_account_must_change_password_before_business_access(
    client: TestClient,
) -> None:
    _admin_username, admin_csrf = _make_admin(client)
    username = f"issue357-open-{uuid.uuid4().hex}"
    temporary_password = _password()
    response = client.post(
        "/api/admin/accounts",
        headers={"X-CSRF-Token": admin_csrf},
        json={
            "username": username,
            "temporaryPassword": temporary_password,
            "reason": "合成开户验收",
        },
    )

    assert response.status_code == 201
    account = response.json()
    assert account["username"] == username
    assert account["role"] == "user"
    assert account["mustChangePassword"] is True
    serialized = response.text
    if temporary_password in serialized or "password_hash" in serialized:
        raise AssertionError("开户响应包含凭据")

    with TestClient(client.app) as new_user:
        login = new_user.post(
            "/api/auth/login",
            json={"username": username, "password": temporary_password},
        )
        assert login.status_code == 200
        assert login.json()["user"]["id"] == account["id"]
        assert login.json()["user"]["mustChangePassword"] is True
        assert new_user.get("/api/cases?scope=mine").status_code == 403

        changed_password = _password()
        changed = new_user.post(
            "/api/auth/change-password",
            headers={"X-CSRF-Token": login.json()["csrfToken"]},
            json={
                "currentPassword": temporary_password,
                "newPassword": changed_password,
            },
        )

        assert changed.status_code == 204
        assert changed.content == b""
        assert new_user.get("/api/auth/session").status_code == 401
        assert new_user.get("/api/cases?scope=mine").status_code == 401
        relogin = new_user.post(
            "/api/auth/login",
            json={"username": username, "password": changed_password},
        )
        assert relogin.status_code == 200
        session = new_user.get("/api/auth/session")
        assert session.status_code == 200
        assert session.json()["user"]["id"] == account["id"]
        assert session.json()["user"]["mustChangePassword"] is False
        assert new_user.get("/api/cases?scope=mine").status_code == 200


def test_admin_reset_revokes_old_sessions_and_preserves_account_identity(
    client: TestClient,
) -> None:
    _admin_username, admin_csrf = _make_admin(client)
    username = f"issue357-reset-{uuid.uuid4().hex}"
    old_password = _password()
    created = client.post(
        "/api/admin/accounts",
        headers={"X-CSRF-Token": admin_csrf},
        json={
            "username": username,
            "temporaryPassword": old_password,
            "reason": "合成开户验收",
        },
    )
    assert created.status_code == 201
    account_id = created.json()["id"]
    new_temporary_password = _password()

    with TestClient(client.app) as first, TestClient(client.app) as second:
        for current in (first, second):
            logged_in = current.post(
                "/api/auth/login",
                json={"username": username, "password": old_password},
            )
            assert logged_in.status_code == 200
        reset = client.post(
            f"/api/admin/accounts/{account_id}/temporary-password",
            headers={"X-CSRF-Token": admin_csrf},
            json={
                "temporaryPassword": new_temporary_password,
                "reason": "合成密码恢复验收",
            },
        )

        assert reset.status_code == 200
        assert reset.json()["id"] == account_id
        assert reset.json()["mustChangePassword"] is True
        for current in (first, second):
            assert current.get("/api/auth/session").status_code == 401
        if old_password in reset.text or new_temporary_password in reset.text:
            raise AssertionError("密码重置响应包含凭据")
        if "password_hash" in reset.text:
            raise AssertionError("密码重置响应包含密码哈希")

    with TestClient(client.app) as recovered:
        old_login = recovered.post(
            "/api/auth/login",
            json={"username": username, "password": old_password},
        )
        assert old_login.status_code == 401
        new_login = recovered.post(
            "/api/auth/login",
            json={"username": username, "password": new_temporary_password},
        )
        assert new_login.status_code == 200
        assert new_login.json()["user"]["id"] == account_id
        assert new_login.json()["user"]["mustChangePassword"] is True


def test_admin_force_logout_invalidates_sessions_without_changing_password(
    client: TestClient,
) -> None:
    _admin_username, admin_csrf = _make_admin(client)
    username = f"issue357-logout-{uuid.uuid4().hex}"
    temporary_password = _password()
    created = client.post(
        "/api/admin/accounts",
        headers={"X-CSRF-Token": admin_csrf},
        json={
            "username": username,
            "temporaryPassword": temporary_password,
            "reason": "合成开户验收",
        },
    )
    assert created.status_code == 201
    account_id = created.json()["id"]
    current_password = _password()

    with TestClient(client.app) as first, TestClient(client.app) as second:
        login = first.post(
            "/api/auth/login",
            json={"username": username, "password": temporary_password},
        )
        changed = first.post(
            "/api/auth/change-password",
            headers={"X-CSRF-Token": login.json()["csrfToken"]},
            json={
                "currentPassword": temporary_password,
                "newPassword": current_password,
            },
        )
        assert changed.status_code == 204
        assert first.get("/api/auth/session").status_code == 401
        first_relogin = first.post(
            "/api/auth/login",
            json={"username": username, "password": current_password},
        )
        assert first_relogin.status_code == 200
        assert first_relogin.json()["user"]["id"] == account_id
        other_login = second.post(
            "/api/auth/login",
            json={"username": username, "password": current_password},
        )
        assert other_login.status_code == 200

        forced = client.post(
            f"/api/admin/accounts/{account_id}/force-logout",
            headers={"X-CSRF-Token": admin_csrf},
            json={"reason": "合成会话撤销验收"},
        )

        assert forced.status_code == 200
        assert forced.json()["account"]["id"] == account_id
        assert forced.json()["revokedSessions"] == 2
        assert first.get("/api/auth/session").status_code == 401
        assert second.get("/api/auth/session").status_code == 401
        if temporary_password in forced.text or current_password in forced.text:
            raise AssertionError("强制退出响应包含凭据")

    with TestClient(client.app) as recovered:
        relogin = recovered.post(
            "/api/auth/login",
            json={"username": username, "password": current_password},
        )
        assert relogin.status_code == 200
        assert relogin.json()["user"]["id"] == account_id
        assert relogin.json()["user"]["mustChangePassword"] is False


def test_admin_can_read_persisted_account_operations_without_credentials(
    client: TestClient,
) -> None:
    admin_username, admin_csrf = _make_admin(client)
    username = f"issue357-audit-{uuid.uuid4().hex}"
    temporary_password = _password()
    opened = client.post(
        "/api/admin/accounts",
        headers={"X-CSRF-Token": admin_csrf},
        json={
            "username": username,
            "temporaryPassword": temporary_password,
            "reason": "合成开户审计验收",
        },
    )
    assert opened.status_code == 201
    duplicate = client.post(
        "/api/admin/accounts",
        headers={"X-CSRF-Token": admin_csrf},
        json={
            "username": username,
            "temporaryPassword": _password(),
            "reason": "合成重复开户拒绝验收",
        },
    )
    assert duplicate.status_code == 409
    first_read = client.get("/api/admin/account-operations")
    second_read = client.get("/api/admin/account-operations")

    assert first_read.status_code == 200
    assert second_read.status_code == 200
    assert first_read.json() == second_read.json()
    operations = first_read.json()["items"]
    success = next(
        item for item in operations if item["targetId"] == opened.json()["id"]
    )
    rejected = next(
        item
        for item in operations
        if item["targetUsername"] == username and item["result"] == "rejected"
    )
    assert success["actorUsername"] == admin_username
    assert success["action"] == "account_open"
    assert success["reason"] == "合成开户审计验收"
    assert success["result"] == "success"
    assert success["createdAt"]
    assert rejected["action"] == "account_open"
    assert rejected["reason"] == "合成重复开户拒绝验收"
    assert rejected["result"] == "rejected"
    serialized = first_read.text
    if temporary_password in serialized or "password_hash" in serialized:
        raise AssertionError("操作记录包含凭据")


def test_account_management_rejects_anonymous_users_and_requires_csrf(
    client: TestClient,
) -> None:
    anonymous_list = client.get("/api/admin/accounts")
    anonymous_open = client.post(
        "/api/admin/accounts",
        json={
            "username": f"issue357-anon-{uuid.uuid4().hex}",
            "temporaryPassword": _password(),
            "reason": "权限拒绝验收",
        },
    )
    assert anonymous_list.status_code == 401
    assert anonymous_open.status_code == 401

    username = f"issue357-user-{uuid.uuid4().hex}"
    user, password = _register(client, username)
    with TestClient(client.app) as ordinary:
        signed_in = ordinary.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        assert signed_in.status_code == 200
        assert ordinary.get("/api/admin/accounts").status_code == 403
        assert ordinary.get("/api/admin/account-operations").status_code == 403
        forbidden = ordinary.post(
            "/api/admin/accounts",
            headers={"X-CSRF-Token": signed_in.json()["csrfToken"]},
            json={
                "username": f"issue357-forbidden-{uuid.uuid4().hex}",
                "temporaryPassword": _password(),
                "reason": "权限拒绝验收",
            },
        )
        assert forbidden.status_code == 403

    _admin_username, _admin_csrf = _make_admin(client)
    csrf_missing = client.post(
        "/api/admin/accounts",
        json={
            "username": f"issue357-csrf-{uuid.uuid4().hex}",
            "temporaryPassword": _password(),
            "reason": "CSRF 拒绝验收",
        },
    )
    assert csrf_missing.status_code == 403


def test_account_validation_errors_do_not_echo_temporary_password(client: TestClient) -> None:
    _admin_username, csrf = _make_admin(client)
    invalid_temporary_password = f"Issue357-{uuid.uuid4().hex}{'x' * 100}!a"
    response = client.post(
        "/api/admin/accounts",
        headers={"X-CSRF-Token": csrf},
        json={
            "username": f"issue357-long-password-{uuid.uuid4().hex}",
            "temporaryPassword": invalid_temporary_password,
            "reason": "合成校验错误脱敏验收",
        },
    )

    assert response.status_code == 422
    if invalid_temporary_password in response.text or '"input"' in response.text:
        raise AssertionError("开户校验响应包含临时密码")
