"""OpenAI-compatible chat client boundary for backend AI features."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class AIClientError(RuntimeError):
    """Raised when the upstream AI provider is unavailable or invalid."""


@dataclass(frozen=True)
class AISettings:
    enabled: bool
    base_url: str
    api_key: str
    models: tuple[str, ...]
    default_model: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> AISettings:
        models = tuple(
            item.strip() for item in os.getenv("AI_MODELS", "").split(",") if item.strip()
        )
        default_model = os.getenv("AI_DEFAULT_MODEL", "").strip()
        timeout_raw = os.getenv("AI_TIMEOUT_SECONDS", "60").strip() or "60"
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = 60.0
        return cls(
            enabled=os.getenv("AI_REVIEW_ENABLED", "false").strip().lower()
            in {"1", "true", "yes", "on"},
            base_url=os.getenv("AI_BASE_URL", "").strip().rstrip("/"),
            api_key=os.getenv("AI_API_KEY", "").strip(),
            models=models,
            default_model=default_model,
            timeout_seconds=max(1.0, timeout_seconds),
        )

    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.models and self.default_model)

    def resolve_model(self, requested_model: str | None = None) -> str:
        model = (requested_model or self.default_model).strip()
        if not model:
            raise ValueError("未配置默认 AI 模型")
        if model not in self.models:
            raise ValueError("请求的 AI 模型不可用")
        return model


def build_chat_messages(
    prompt_text: str, system_content: str = ""
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system_content:
        messages.append({"role": "system", "content": system_content})
    messages.append({"role": "user", "content": prompt_text})
    return messages


def call_chat_completion(
    prompt_text: str,
    model: str,
    settings: AISettings | None = None,
    *,
    system_content: str = "",
) -> str:
    settings = settings or AISettings.from_env()
    parsed_base_url = urllib.parse.urlparse(settings.base_url)
    if parsed_base_url.scheme not in {"http", "https"}:
        raise AIClientError("AI 服务地址必须使用 HTTP 或 HTTPS")

    payload = {
        "model": model,
        "messages": build_chat_messages(prompt_text, system_content),
        "temperature": 0.2,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{settings.base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.timeout_seconds) as response:  # nosec B310
            raw = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AIClientError("AI 服务暂不可用") from exc

    try:
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise AIClientError("AI 服务返回格式无效") from exc

    if not isinstance(content, str):
        raise AIClientError("AI 服务返回内容无效")
    return content


def extract_json_object(text: str) -> tuple[dict[str, Any] | None, str | None]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()

    decoder = json.JSONDecoder()
    for index, char in enumerate(candidate):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(candidate[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed, None
    return None, "AI 返回内容中未找到有效 JSON 对象"
