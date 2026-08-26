from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

CHAT_BODY = {"messages": [{"role": "user", "content": "测试问题"}]}
DISCOVERY_BODY = {
    "baseUrl": "https://custom.invalid/v1",
    "apiKey": "discovery-only-key",
}
CUSTOM_SETTINGS_RESPONSE = {
    "mode": "custom",
    "baseUrl": "https://custom.invalid/v1",
    "model": "custom-model",
    "hasApiKey": True,
    "configured": True,
    "effectiveSource": "custom",
    "effectiveModel": "custom-model",
}


class FakeProvider:
    def __init__(self) -> None:
        self.models = []

    def chat(self, _messages: list[dict], model: str):
        self.models.append(model)
        yield "第一段"
        yield "第二段"


class FakeDiscoveryProvider:
    def models(self):
        return ["custom-a", "custom-b", "custom-a"]


def login(client: TestClient, username: str = "user", password: str = "user123"):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}
    ).json()


def configure_platform(client: TestClient, tmp_path) -> None:
    key_file = tmp_path / "platform-key"
    key_file.write_text("platform-test-key", encoding="utf-8")
    client.app.state.settings = replace(
        client.app.state.settings,
        ai_base_url="https://8.8.8.8/v1",
        ai_api_key_file=str(key_file),
        ai_models=("platform-a", "platform-b"),
        ai_default_model="platform-a",
    )


def configure_app_secret(client: TestClient, tmp_path) -> None:
    secret_file = tmp_path / "app-secret"
    secret_file.write_text("test-only-app-secret", encoding="utf-8")
    client.app.state.settings = replace(
        client.app.state.settings, app_secret_file=str(secret_file)
    )


def save_custom(
    client: TestClient,
    csrf_token: str,
    api_key: str = "custom-key",
    base_url: str = "https://custom.invalid/v1",
):
    return client.put(
        "/api/ai/settings",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "mode": "custom",
            "baseUrl": base_url,
            "apiKey": api_key,
            "model": "custom-model",
        },
    )


def csrf_header(auth: dict) -> dict[str, str]:
    return {"X-CSRF-Token": auth["csrfToken"]}


def post_chat(client: TestClient, auth: dict):
    return client.post("/api/ai/chat", headers=csrf_header(auth), json=CHAT_BODY)


def save_admin_fallback(client: TestClient, auth: dict, model: str):
    return client.put(
        "/api/admin/ai/settings",
        headers=csrf_header(auth),
        json={"fallbackModel": model},
    )


def assert_normalized_stream(response) -> None:
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == (
        'event: token\ndata: {"text":"第一段"}\n\n'
        'event: token\ndata: {"text":"第二段"}\n\n'
        "event: done\ndata: {}\n\n"
    )


def assert_custom_record(client: TestClient) -> None:
    record = client.app.state.database.ai_user_settings.find_one()
    assert record["_id"] == "u-user-demo"
    assert b"custom-key" not in bytes(record["encryptedApiKey"])
    assert "apiKey" not in record


def assert_custom_settings_response(response) -> None:
    assert response.status_code == 200
    assert response.json() == CUSTOM_SETTINGS_RESPONSE


def assert_preserved_key(before: dict, after: dict) -> None:
    assert before["encryptedApiKey"] == after["encryptedApiKey"]


def test_user_ai_settings_are_private_and_report_unconfigured_platform(
    client: TestClient,
) -> None:
    assert client.get("/api/ai/settings").status_code == 401
    login(client)

    response = client.get("/api/ai/settings")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "automatic",
        "baseUrl": None,
        "model": None,
        "hasApiKey": False,
        "configured": False,
        "effectiveSource": None,
        "effectiveModel": None,
    }


def test_admin_fallback_overrides_the_platform_default(
    client: TestClient, tmp_path
) -> None:
    configure_platform(client, tmp_path)
    login(client)
    assert client.get("/api/ai/settings").json()["effectiveModel"] == "platform-a"
    admin = login(client, "admin", "admin123")

    response = save_admin_fallback(client, admin, "platform-b")
    assert response.status_code == 200
    assert response.json() == {
        "fallbackModel": "platform-b",
        "availableModels": ["platform-a", "platform-b"],
        "configured": True,
    }
    login(client)
    settings = client.get("/api/ai/settings").json()
    assert settings["effectiveSource"] == "adminFallback"
    assert settings["effectiveModel"] == "platform-b"


def test_platform_chat_requires_csrf_and_streams_normalized_events(
    client: TestClient,
    tmp_path,
) -> None:
    configure_platform(client, tmp_path)
    provider = FakeProvider()
    client.app.state.ai_provider = provider
    auth = login(client)

    assert client.post("/api/ai/chat", json=CHAT_BODY).status_code == 403
    response = post_chat(client, auth)

    assert_normalized_stream(response)
    assert provider.models == ["platform-a"]


def test_user_can_persist_automatic_mode(client: TestClient, tmp_path) -> None:
    configure_platform(client, tmp_path)
    auth = login(client)

    response = client.put(
        "/api/ai/settings",
        headers=csrf_header(auth),
        json={"mode": "automatic"},
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "automatic"
    assert response.json()["effectiveSource"] == "default"
    assert client.get("/api/ai/settings").json() == response.json()


def test_custom_settings_encrypt_key_and_never_return_it(client: TestClient, tmp_path) -> None:
    configure_app_secret(client, tmp_path)
    auth = login(client)

    response = save_custom(client, auth["csrfToken"])

    assert_custom_settings_response(response)
    assert_custom_record(client)


def configure_custom_environment(client, tmp_path) -> None:
    configure_platform(client, tmp_path)
    configure_app_secret(client, tmp_path)


def _saved_custom_record(client: TestClient, auth: dict) -> dict:
    response = save_custom(client, auth["csrfToken"])
    assert response.status_code == 200
    return client.app.state.database.ai_user_settings.find_one()


def test_custom_chat_uses_custom_model_and_blank_key_keeps_secret(
    client: TestClient,
    tmp_path,
) -> None:
    configure_custom_environment(client, tmp_path)
    auth = login(client)
    before = _saved_custom_record(client, auth)
    response = save_custom(
        client,
        auth["csrfToken"],
        "",
        " https://custom.invalid/v1/ ",
    )
    provider, chat_response = _custom_chat(client, auth)
    assert response.status_code == 200
    after = client.app.state.database.ai_user_settings.find_one()
    assert_preserved_key(before, after)
    assert chat_response.status_code == 200
    assert provider.models == ["custom-model"]


def _custom_chat(client: TestClient, auth: dict) -> tuple[FakeProvider, object]:
    provider = FakeProvider()
    client.app.state.ai_provider = provider
    return provider, post_chat(client, auth)


def test_custom_url_change_requires_new_key_and_keeps_record(
    client: TestClient,
    tmp_path,
) -> None:
    configure_app_secret(client, tmp_path)
    auth = login(client)
    before = _saved_custom_record(client, auth)

    response = save_custom(
        client,
        auth["csrfToken"],
        api_key="",
        base_url="https://other.invalid/v1/",
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Base URL 变更后必须提供新的 API 密钥"
    assert client.app.state.database.ai_user_settings.find_one() == before


def test_custom_url_change_with_new_key_replaces_encrypted_key(
    client: TestClient,
    tmp_path,
) -> None:
    configure_app_secret(client, tmp_path)
    auth = login(client)
    before = _saved_custom_record(client, auth)

    response = save_custom(
        client,
        auth["csrfToken"],
        api_key="new-key",
        base_url=" https://other.invalid/v1/ ",
    )
    after = client.app.state.database.ai_user_settings.find_one()

    assert response.status_code == 200
    assert response.json()["baseUrl"] == "https://other.invalid/v1"
    assert after["encryptedApiKey"] != before["encryptedApiKey"]


def test_model_discovery_requires_csrf_and_does_not_echo_key(
    client: TestClient,
) -> None:
    auth = login(client)
    client.app.state.ai_discovery_provider = FakeDiscoveryProvider()

    denied = client.post("/api/ai/models/discover", json=DISCOVERY_BODY)
    assert denied.status_code == 403
    response = client.post(
        "/api/ai/models/discover",
        headers=csrf_header(auth),
        json=DISCOVERY_BODY,
    )

    assert response.status_code == 200
    assert response.json() == {"models": ["custom-a", "custom-b"]}
    assert DISCOVERY_BODY["apiKey"] not in response.text
    assert client.app.state.database.ai_user_settings.count_documents({}) == 0


def test_model_discovery_rate_limit_returns_429(client: TestClient) -> None:
    auth = login(client)
    client.app.state.ai_discovery_provider = FakeDiscoveryProvider()

    responses = [
        client.post(
            "/api/ai/models/discover",
            headers=csrf_header(auth),
            json=DISCOVERY_BODY,
        )
        for _index in range(6)
    ]

    assert all(response.status_code == 200 for response in responses[:5])
    assert responses[-1].status_code == 429


def test_broken_custom_secret_never_falls_back_to_platform(
    client: TestClient,
    tmp_path,
) -> None:
    configure_platform(client, tmp_path)
    configure_app_secret(client, tmp_path)
    auth = login(client)
    assert save_custom(client, auth["csrfToken"]).status_code == 200
    replacement = tmp_path / "replacement-secret"
    replacement.write_text("different-test-secret", encoding="utf-8")
    client.app.state.settings = replace(
        client.app.state.settings, app_secret_file=str(replacement)
    )

    response = post_chat(client, auth)

    assert response.status_code == 503
    assert response.json() == {"detail": "个人 AI 配置不可用"}


def test_chat_rejects_excessive_total_prompt(client: TestClient) -> None:
    auth = login(client)
    body = {
        "messages": [{"role": "user", "content": "x" * 20000} for _index in range(6)]
    }

    response = client.post(
        "/api/ai/chat",
        headers=csrf_header(auth),
        json=body,
    )

    assert response.status_code == 422


def test_chat_rate_limit_is_shared_in_database(client: TestClient, tmp_path) -> None:
    configure_platform(client, tmp_path)
    client.app.state.ai_provider = FakeProvider()
    auth = login(client)

    responses = [post_chat(client, auth) for _index in range(21)]

    assert all(response.status_code == 200 for response in responses[:20])
    assert responses[-1].status_code == 429


class OversizedProvider:
    def chat(self, _messages: list[dict], _model: str):
        for _index in range(300):
            yield "x" * 1024


def test_chat_stream_stops_at_output_limit(client: TestClient, tmp_path) -> None:
    configure_platform(client, tmp_path)
    client.app.state.ai_provider = OversizedProvider()
    auth = login(client)

    response = post_chat(client, auth)

    assert response.status_code == 200
    assert "event: error" in response.text
    assert len(response.content) < 270 * 1024


def test_chat_concurrency_limit_does_not_reuse_active_slots(
    client: TestClient,
    tmp_path,
) -> None:
    configure_platform(client, tmp_path)
    auth = login(client)
    now = datetime.now(UTC)
    for slot in range(2):
        client.app.state.database.ai_usage.insert_one(
            {
                "_id": f"concurrent:chat:user:u-user-demo:{slot}",
                "token": f"active-{slot}",
                "expiresAt": now + timedelta(minutes=1),
            }
        )

    response = post_chat(client, auth)

    assert response.status_code == 429
