from __future__ import annotations

from fastapi.testclient import TestClient

CURRENT_PASSWORD = "Demo-10000001-2026!"
NEW_PASSWORD = "Roster-Changed-2026!"


def login(client: TestClient, username: str, password: str):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )


def test_login_and_session_expose_forced_password_change(client: TestClient) -> None:
    response = login(client, "10000001", "Demo-10000001-2026!")

    assert response.status_code == 200
    assert response.json()["user"]["mustChangePassword"] is True
    assert client.get("/api/auth/session").json()["user"]["mustChangePassword"] is True

    demo = login(client, "user", "user123")
    assert demo.json()["user"]["mustChangePassword"] is False


def test_forced_password_change_blocks_optional_business_routes(
    client: TestClient,
) -> None:
    login(client, "10000001", CURRENT_PASSWORD)

    response = client.get("/api/cases/c-02")

    assert response.status_code == 403
    assert response.json() == {"detail": "请先修改初始密码"}


def test_login_rejects_extra_fields(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "user123", "unexpected": True},
    )

    assert response.status_code == 422


def test_password_validation_does_not_echo_the_password(client: TestClient) -> None:
    auth = login(client, "10000001", CURRENT_PASSWORD).json()
    secret = "Secret-" + ("x" * 130)

    response = change_password(client, auth["csrfToken"], CURRENT_PASSWORD, secret)

    assert response.status_code == 422
    assert secret not in response.text
    assert client.get("/api/auth/session").status_code == 200


def test_password_change_requires_csrf_and_the_current_password(
    client: TestClient,
) -> None:
    auth = login(client, "10000001", CURRENT_PASSWORD).json()
    body = {"currentPassword": "Wrong-Current-2026!", "newPassword": NEW_PASSWORD}

    assert client.post("/api/auth/change-password", json=body).status_code == 403
    response = client.post(
        "/api/auth/change-password",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json=body,
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "当前密码错误"}
    assert all(password not in response.text for password in body.values())
    assert client.get("/api/auth/session").status_code == 200


def test_password_change_rejects_extra_fields(client: TestClient) -> None:
    auth = login(client, "10000001", CURRENT_PASSWORD).json()
    body = {"currentPassword": CURRENT_PASSWORD, "newPassword": NEW_PASSWORD}
    body["unexpected"] = True

    response = client.post(
        "/api/auth/change-password",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json=body,
    )

    assert response.status_code == 422
    assert client.get("/api/auth/session").status_code == 200


def change_password(client: TestClient, csrf: str, current: str, new: str):
    return client.post(
        "/api/auth/change-password",
        headers={"X-CSRF-Token": csrf},
        json={"currentPassword": current, "newPassword": new},
    )


def test_password_change_revokes_all_sessions_and_requires_login(
    client: TestClient,
) -> None:
    first = login(client, "10000001", CURRENT_PASSWORD).json()
    with TestClient(client.app) as other:
        assert login(other, "10000001", CURRENT_PASSWORD).status_code == 200
        changed = change_password(
            client, first["csrfToken"], CURRENT_PASSWORD, NEW_PASSWORD
        )
        assert changed.status_code == 204
        assert client.get("/api/auth/session").status_code == 401
        assert other.get("/api/auth/session").status_code == 401
    assert login(client, "10000001", CURRENT_PASSWORD).status_code == 401
    renewed = login(client, "10000001", NEW_PASSWORD)
    assert renewed.status_code == 200
    assert renewed.json()["user"]["mustChangePassword"] is False


def test_password_change_rejects_a_weak_new_password(client: TestClient) -> None:
    auth = login(client, "10000001", CURRENT_PASSWORD).json()

    response = change_password(client, auth["csrfToken"], CURRENT_PASSWORD, "too-short")

    assert response.status_code == 422
    assert response.json() == {"detail": "新密码至少 12 个字符"}
    assert client.get("/api/auth/session").status_code == 200


def test_password_change_rejects_the_current_password(client: TestClient) -> None:
    auth = login(client, "10000001", CURRENT_PASSWORD).json()

    response = change_password(
        client, auth["csrfToken"], CURRENT_PASSWORD, CURRENT_PASSWORD
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "新密码不能与当前密码相同"}
    assert client.get("/api/auth/session").status_code == 200
