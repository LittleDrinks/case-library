from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _login(client: TestClient):
    return client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )


def test_login_reads_the_authenticated_user_once(
    client: TestClient, monkeypatch
) -> None:
    users = client.app.state.database.users
    original = users.find_one
    calls = 0

    def counted_find_one(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(users, "find_one", counted_find_one)
    assert _login(client).status_code == 200
    assert calls == 1


@pytest.mark.parametrize(
    "update",
    (
        {"$set": {"status": "disabled"}},
        {"$inc": {"token_version": 1}},
    ),
)
def test_live_user_state_revokes_an_existing_session(
    client: TestClient, update
) -> None:
    assert _login(client).status_code == 200
    client.app.state.database.users.update_one({"username": "user"}, update)

    response = client.get("/api/auth/session")

    assert response.status_code == 401
