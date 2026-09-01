from __future__ import annotations

import asyncio

import httpx
import httpx2
import pytest

from app.modules.ai import provider, transport


def public_dns(*_args, **_kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def mock_discovery(monkeypatch, handler, base_url="https://models.example/v1", internal=False):
    if internal:
        monkeypatch.setattr(transport.socket, "gethostbyname", lambda _host: "127.0.0.1")
    else:
        monkeypatch.setattr(transport.socket, "getaddrinfo", public_dns)
    monkeypatch.setattr(provider, "_transport", lambda *_args: httpx.MockTransport(handler))
    return provider.OpenAIModelDiscovery(base_url, "test-key", 1, internal)


def test_malformed_model_id_becomes_provider_error(monkeypatch) -> None:
    def handler(_request):
        return httpx.Response(200, json={"data": [{"id": 7}]})

    with pytest.raises(provider.ProviderError):
        mock_discovery(monkeypatch, handler).models()


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.8", "169.254.169.254", "::ffff:10.0.0.8"]
)
def test_private_model_provider_is_rejected_before_request(monkeypatch, address: str) -> None:
    monkeypatch.setattr(
        transport.socket, "getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", (address, 443))],
    )
    with pytest.raises(provider.ProviderError):
        provider.OpenAIModelDiscovery("https://models.example/v1", "test-key", 1).models()


def test_discovery_uses_openai_sdk_with_pinned_transport(monkeypatch) -> None:
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": "model-a"}]})

    discovery = mock_discovery(monkeypatch, handler)
    assert discovery.models() == ["model-a"]
    assert seen[0].headers["authorization"] == "Bearer test-key"


def test_internal_http_provider_defaults_to_port_80(monkeypatch) -> None:
    monkeypatch.setattr(transport.socket, "gethostbyname", lambda _host: "127.0.0.1")
    target = provider._target("http://ai-provider/v1", "models", True)
    assert target.port == 80
    assert target.secure is False


def test_public_transport_rejects_non_https_and_url_ambiguity() -> None:
    for url in (
        "http://models.example/v1",
        "https://user:pass@models.example/v1",
        "https://models.example/v1?redirect=http://evil",
    ):
        with pytest.raises(transport.ProviderError):
            transport.parse_provider_url(url)


def test_open_model_constructs_an_openai_chat_model(monkeypatch) -> None:
    monkeypatch.setattr(provider, "RestrictedProviderTransport", lambda *_args: httpx2.MockTransport(_response))
    selection = type("Selection", (), {
        "base_url": "http://ai-provider:8080/v1",
        "api_key": "test-key", "model": "model-a", "timeout_seconds": 1,
    })()

    async def collect():
        async with provider.open_model(selection, True) as model:
            return model

    model = asyncio.run(collect())
    assert model.model_name == "model-a"


def _response(_request):
    body = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
    return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body)
