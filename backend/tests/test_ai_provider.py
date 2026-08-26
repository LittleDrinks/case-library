from __future__ import annotations

import json

import httpx
import pytest

from app.modules.ai import provider
from app.modules.ai.models import WritingCandidate


def public_dns(*_args, **_kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def mock_provider(monkeypatch, handler, base_url="https://models.example/v1", internal=False):
    if internal:
        monkeypatch.setattr(provider.socket, "gethostbyname", lambda _host: "127.0.0.1")
    else:
        monkeypatch.setattr(provider.socket, "getaddrinfo", public_dns)
    monkeypatch.setattr(provider, "_transport", lambda *_args: httpx.MockTransport(handler))
    return provider.OpenAICompatibleProvider(base_url, "test-key", 1, internal)


def test_malformed_model_id_becomes_provider_error(monkeypatch) -> None:
    def handler(_request):
        return httpx.Response(200, json={"data": [{"id": 7}]})

    client = mock_provider(monkeypatch, handler)
    with pytest.raises(provider.ProviderError):
        client.models()


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.8", "169.254.169.254", "::ffff:10.0.0.8"],
)
def test_private_model_provider_is_rejected_before_request(
    monkeypatch, address: str
) -> None:
    monkeypatch.setattr(
        provider.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", (address, 443))],
    )
    client = provider.OpenAICompatibleProvider(
        "https://models.example/v1", "test-key", 1
    )
    with pytest.raises(provider.ProviderError):
        client.models()


def stream_handler(_request):
    payload = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=payload)


def test_test_environment_can_reach_an_internal_fake_provider(monkeypatch) -> None:
    client = mock_provider(
        monkeypatch, stream_handler, "http://ai-provider:8080/v1", internal=True
    )
    result = client.chat([{"role": "user", "content": "问题"}], "model-a")
    assert list(result) == ["ok"]


def test_provider_uses_openai_sdk_with_httpx_transport(monkeypatch) -> None:
    seen = []

    def handler(request):
        seen.append(request)
        return stream_handler(request)

    client = mock_provider(monkeypatch, handler)
    assert list(client.chat([{"role": "user", "content": "问题"}], "model-a")) == ["ok"]
    assert seen[0].headers["authorization"] == "Bearer test-key"


def test_internal_http_provider_defaults_to_port_80(monkeypatch) -> None:
    monkeypatch.setattr(provider.socket, "gethostbyname", lambda _host: "127.0.0.1")
    target = provider._target("http://ai-provider/v1", "models", True)
    assert target.port == 80


def test_chat_rejects_an_incomplete_stream(monkeypatch) -> None:
    def handler(_request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=b"data: {}\n\n")

    client = mock_provider(monkeypatch, handler)
    with pytest.raises(provider.ProviderError):
        list(client.chat([{"role": "user", "content": "问题"}], "model-a"))


def test_chat_rejects_an_oversized_provider_response(monkeypatch) -> None:
    def handler(_request):
        return httpx.Response(200, content=b"x" * (provider.MAX_CHAT_BYTES + 1))

    client = mock_provider(monkeypatch, handler)
    with pytest.raises(provider.ProviderError):
        list(client.chat([{"role": "user", "content": "问题"}], "model-a"))


def structured_handler(_request):
    content = json.dumps({"kind": "writing_candidate", "text": "候选", "reason": "理由"})
    payload = {
        "id": "response-id",
        "object": "chat.completion",
        "created": 1,
        "model": "model-a",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content, "refusal": None},
            "logprobs": None,
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    return httpx.Response(200, json=payload)


def test_structured_uses_sdk_parsed_pydantic_model(monkeypatch) -> None:
    client = mock_provider(monkeypatch, structured_handler)
    result = client.structured(
        [{"role": "user", "content": "问题"}], "model-a", WritingCandidate
    )
    assert isinstance(result, WritingCandidate)
    assert result.text == "候选"
