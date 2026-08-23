from __future__ import annotations

import pytest

from app.core.config import Settings


def ai_environment(tmp_path) -> dict[str, str]:
    key_file = tmp_path / "ai-key"
    key_file.write_text("test-only", encoding="utf-8")
    return {
        "APP_SECRET_FILE": str(tmp_path / "app-secret"),
        "AI_BASE_URL": "https://provider.invalid/v1",
        "AI_API_KEY_FILE": str(key_file),
        "AI_MODELS": "model-a, model-b",
        "AI_DEFAULT_MODEL": "model-b",
        "AI_TIMEOUT_SECONDS": "17",
    }


def test_ai_settings_are_loaded_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    values = ai_environment(tmp_path)
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    settings = Settings.from_environment()

    assert settings.app_secret_file == values["APP_SECRET_FILE"]
    assert settings.ai_base_url == values["AI_BASE_URL"]
    assert settings.ai_api_key_file == values["AI_API_KEY_FILE"]
    assert settings.ai_models == ("model-a", "model-b")
    assert settings.ai_default_model == "model-b"
    assert settings.ai_timeout_seconds == 17
