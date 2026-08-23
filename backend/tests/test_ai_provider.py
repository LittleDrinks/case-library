from __future__ import annotations

import json
import threading

import pytest

from app.modules.ai import provider


class FakeResponse:
    status = 200
    headers = {"content-type": "application/json"}

    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode()
        self.consumed = False

    def read(self, _limit: int) -> bytes:
        if self.consumed:
            return b""
        self.consumed = True
        return self.payload

    def release_conn(self) -> None:
        return None

    def close(self) -> None:
        return None


class FakePool:
    def __init__(self, payload: dict):
        self.response = FakeResponse(payload)

    def request(self, *_args, **_kwargs):
        return self.response

    def close(self) -> None:
        return None


class StreamResponse:
    status = 200
    headers = {"content-type": "text/event-stream"}

    def __init__(self, chunks: list[bytes]):
        self.chunks = iter(chunks)
        self.closed = False

    def read(self, _limit: int, **_kwargs) -> bytes:
        return next(self.chunks, b"")

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        return None


class BlockingResponse(StreamResponse):
    def __init__(self):
        super().__init__([])
        self.release = threading.Event()

    def read(self, _limit: int, **_kwargs) -> bytes:
        self.release.wait(1)
        return b""

    def close(self) -> None:
        super().close()
        self.release.set()


class StreamPool:
    def __init__(self, response):
        self.response = response
        self.closed = False

    def request(self, *_args, **_kwargs):
        return self.response

    def close(self) -> None:
        self.closed = True


def public_dns(*_args, **_kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def test_malformed_model_id_becomes_provider_error(monkeypatch) -> None:
    monkeypatch.setattr(provider.socket, "getaddrinfo", public_dns)
    monkeypatch.setattr(
        provider, "_pool", lambda *_args: FakePool({"data": [{"id": 7}]})
    )
    client = provider.OpenAICompatibleProvider(
        "https://models.example/v1", "test-key", 5
    )

    with pytest.raises(provider.ProviderError):
        client.models()


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.8", "169.254.169.254", "::ffff:10.0.0.8"],
)
def test_private_model_provider_is_rejected_before_request(
    monkeypatch,
    address: str,
) -> None:
    monkeypatch.setattr(
        provider.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", (address, 443))],
    )
    monkeypatch.setattr(
        provider, "_pool", lambda *_args: pytest.fail("network request attempted")
    )
    client = provider.OpenAICompatibleProvider(
        "https://models.example/v1", "test-key", 5
    )

    with pytest.raises(provider.ProviderError):
        client.models()


def stream_client(monkeypatch, response, timeout: float = 1):
    pool = StreamPool(response)
    monkeypatch.setattr(provider.socket, "getaddrinfo", public_dns)
    monkeypatch.setattr(provider, "_pool", lambda *_args: pool)
    client = provider.OpenAICompatibleProvider(
        "https://models.example/v1", "test-key", timeout
    )
    return client, pool


def test_test_environment_can_reach_an_internal_fake_provider(monkeypatch) -> None:
    response = StreamResponse(
        [
            b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n',
            b"data: [DONE]\n\n",
        ]
    )
    pool = StreamPool(response)
    monkeypatch.setattr(provider.socket, "gethostbyname", lambda _host: "127.0.0.1")
    monkeypatch.setattr(provider, "_pool", lambda *_args: pool)
    client = provider.OpenAICompatibleProvider(
        "http://ai-provider:8080/v1", "test-key", 1, allow_internal=True
    )

    assert list(client.chat([{"role": "user", "content": "问题"}], "model-a")) == ["ok"]


def test_internal_http_provider_defaults_to_port_80(monkeypatch) -> None:
    monkeypatch.setattr(provider.socket, "gethostbyname", lambda _host: "127.0.0.1")

    target = provider._target("http://ai-provider/v1", "models", True)

    assert target.port == 80


def test_chat_deadline_closes_a_silent_provider(monkeypatch) -> None:
    response = BlockingResponse()
    client, pool = stream_client(monkeypatch, response, 0.01)

    with pytest.raises(provider.ProviderError):
        list(client.chat([{"role": "user", "content": "问题"}], "model-a"))

    assert response.closed is True
    assert pool.closed is True


def test_chat_rejects_an_oversized_sse_frame(monkeypatch) -> None:
    response = StreamResponse([b"data: " + b"x" * (64 * 1024 + 1), b""])
    client, pool = stream_client(monkeypatch, response)

    with pytest.raises(provider.ProviderError):
        list(client.chat([{"role": "user", "content": "问题"}], "model-a"))

    assert response.closed is True
    assert pool.closed is True
