from __future__ import annotations

import asyncio
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


DRIP_SECONDS = 0.02
DEADLINE_TEST_TIMEOUT = 0.3
GUARD_SECONDS = 5.0


class _SlowDripResponse:
    status = 200
    headers = {"content-type": "text/event-stream"}

    def __init__(self) -> None:
        self.reads = 0
        self.closed = False

    def read1(self, _size: int) -> bytes:
        self.reads += 1
        time.sleep(DRIP_SECONDS)
        return b"01234567"

    def shutdown(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        return None


class _SlowDripPool:
    def __init__(self) -> None:
        self.response = _SlowDripResponse()

    def request(self, *_args, **_kwargs) -> _SlowDripResponse:
        return self.response

    def close(self) -> None:
        return None


def test_stream_total_deadline_stops_slow_drip(monkeypatch) -> None:
    pool = _SlowDripPool()
    monkeypatch.setattr(transport, "_provider_pool", lambda *_args: pool)
    model_transport = transport.RestrictedProviderTransport(
        "http://127.0.0.1:9/v1", DEADLINE_TEST_TIMEOUT, True
    )

    async def scenario() -> None:
        request = httpx2.Request("POST", "http://127.0.0.1:9/v1/chat/completions", content=b"{}")
        response = await model_transport.handle_async_request(request)
        with pytest.raises(asyncio.TimeoutError):
            async for _chunk in response.aiter_bytes():
                pass
        assert pool.response.closed and pool.response.reads > 0

    asyncio.run(asyncio.wait_for(scenario(), GUARD_SECONDS))


SILENCE_TIMEOUT = 0.5
SILENCE_DRIP_AT = 0.3
DRIP_CHUNK = b'data: {"choices":[{"delta":{"content":"drip"}}]}\n\n'


class _SilenceHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args) -> None:
        return

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        time.sleep(SILENCE_DRIP_AT)
        self.wfile.write(DRIP_CHUNK)
        self.wfile.flush()
        self.server.release.wait(timeout=5)


class _SilenceServer:
    def __enter__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _SilenceHandler)
        self.httpd.release = threading.Event()
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_args) -> None:
        self.httpd.release.set()
        self.httpd.server_close()
        self.thread.join(timeout=2)

    @property
    def port(self) -> int:
        return self.httpd.server_port


def test_silent_provider_cleanup_meets_one_total_deadline() -> None:
    with _SilenceServer() as server:
        url = f"http://127.0.0.1:{server.port}/v1"
        streaming = transport.RestrictedProviderTransport(url, SILENCE_TIMEOUT, True)

        async def scenario():
            request = httpx2.Request("POST", f"{url}/chat/completions", content=b"{}")
            response = await streaming.handle_async_request(request)
            started, chunks = asyncio.get_running_loop().time(), []
            with pytest.raises(asyncio.TimeoutError):
                async for chunk in response.aiter_bytes():
                    chunks.append(chunk)
            return chunks, asyncio.get_running_loop().time() - started

        chunks, elapsed = asyncio.run(asyncio.wait_for(scenario(), GUARD_SECONDS))
    assert b"".join(chunks) == DRIP_CHUNK
    assert 0.9 * SILENCE_TIMEOUT <= elapsed < 1.3 * SILENCE_TIMEOUT
