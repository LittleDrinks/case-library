from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from app.modules.ai.service import AIConfigurationError, resolve_provider


DISCOVERY_BODY = {
    "baseUrl": "https://custom.invalid/v1",
    "apiKey": "discovery-only-key",
}


class FakeDiscoveryProvider:
    def models(self):
        return ["custom-a", "custom-b", "custom-a"]


def login(client: TestClient, username: str = "user", password: str = "user123"):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}
    ).json()


def csrf_header(auth: dict) -> dict[str, str]:
    return {"X-CSRF-Token": auth["csrfToken"]}


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
    api_key="custom-key",
    base_url="https://custom.invalid/v1",
):
    return client.put(
        "/api/ai/settings",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "mode": "custom", "baseUrl": base_url,
            "apiKey": api_key, "model": "custom-model",
        },
    )


def test_user_ai_settings_are_private_and_report_unconfigured_platform(client: TestClient) -> None:
    assert client.get("/api/ai/settings").status_code == 401
    login(client)
    assert client.get("/api/ai/settings").json() == {
        "mode": "automatic", "baseUrl": None, "model": None,
        "hasApiKey": False, "configured": False,
        "effectiveSource": None, "effectiveModel": None,
    }


def test_admin_fallback_overrides_the_platform_default(client: TestClient, tmp_path) -> None:
    configure_platform(client, tmp_path)
    login(client)
    admin = login(client, "admin", "admin123")
    response = client.put(
        "/api/admin/ai/settings", headers=csrf_header(admin),
        json={"fallbackModel": "platform-b"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "fallbackModel": "platform-b", "availableModels": ["platform-a", "platform-b"],
        "configured": True,
    }


def test_custom_settings_encrypt_key_and_preserve_it_on_blank_update(client: TestClient, tmp_path) -> None:
    configure_app_secret(client, tmp_path)
    auth = login(client)
    first = save_custom(client, auth["csrfToken"])
    before = client.app.state.database.ai_user_settings.find_one()
    second = save_custom(client, auth["csrfToken"], "", " https://custom.invalid/v1/ ")
    after = client.app.state.database.ai_user_settings.find_one()
    assert first.status_code == second.status_code == 200
    assert before["encryptedApiKey"] == after["encryptedApiKey"]
    assert "apiKey" not in second.json()


def test_custom_url_change_requires_a_new_key(client: TestClient, tmp_path) -> None:
    configure_app_secret(client, tmp_path)
    auth = login(client)
    save_custom(client, auth["csrfToken"])
    response = save_custom(client, auth["csrfToken"], "", "https://other.invalid/v1/")
    assert response.status_code == 422
    assert response.json()["detail"] == "Base URL 变更后必须提供新的 API 密钥"


def test_broken_custom_secret_is_not_replaced_by_platform(client: TestClient, tmp_path) -> None:
    configure_platform(client, tmp_path)
    configure_app_secret(client, tmp_path)
    auth = login(client)
    assert save_custom(client, auth["csrfToken"]).status_code == 200
    replacement = tmp_path / "replacement-secret"
    replacement.write_text("different-test-secret", encoding="utf-8")
    client.app.state.settings = replace(
        client.app.state.settings, app_secret_file=str(replacement)
    )
    try:
        resolve_provider(client.app.state.database, client.app.state.settings, auth["user"]["id"])
    except AIConfigurationError as error:
        assert str(error) == "个人 AI 配置不可用"
    else:
        raise AssertionError("broken custom secret unexpectedly fell back")


def test_model_discovery_requires_csrf_deduplicates_and_does_not_echo_key(client: TestClient) -> None:
    auth = login(client)
    client.app.state.ai_discovery_provider = FakeDiscoveryProvider()
    denied = client.post("/api/ai/models/discover", json=DISCOVERY_BODY)
    response = client.post(
        "/api/ai/models/discover", headers=csrf_header(auth), json=DISCOVERY_BODY
    )
    assert denied.status_code == 403
    assert response.status_code == 200
    assert response.json() == {"models": ["custom-a", "custom-b"]}
    assert DISCOVERY_BODY["apiKey"] not in response.text
    assert client.app.state.database.ai_usage.count_documents({"token": {"$exists": True}}) == 0


def test_model_discovery_rate_limit_is_database_backed(client: TestClient) -> None:
    auth = login(client)
    client.app.state.ai_discovery_provider = FakeDiscoveryProvider()
    responses = [client.post(
        "/api/ai/models/discover", headers=csrf_header(auth), json=DISCOVERY_BODY
    ) for _index in range(6)]
    assert all(response.status_code == 200 for response in responses[:5])
    assert responses[-1].status_code == 429


def test_legacy_ai_routes_are_absent(client: TestClient) -> None:
    paths = client.app.openapi()["paths"]
    assert "/api/ai/chat" not in paths
    assert "/api/cases/{case_id}/ai/chat" not in paths
