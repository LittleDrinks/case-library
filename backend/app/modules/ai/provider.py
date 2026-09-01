from __future__ import annotations

import socket
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpcore
import httpx
import httpx2
from openai import OpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.modules.ai.transport import (
    ProviderError,
    RestrictedProviderTransport,
    Target,
    parse_provider_url,
    provider_hostname,
    resolve_public_addresses,
)


MAX_MODELS = 200
MAX_MODELS_BYTES = 1024 * 1024


def _target(base_url: str, endpoint: str, allow_internal: bool = False) -> Target:
    parts = parse_provider_url(base_url, allow_internal)
    host = provider_hostname(parts.hostname)
    secure = parts.scheme == "https"
    port = parts.port or (443 if secure else 80)
    try:
        ip = socket.gethostbyname(host) if allow_internal and not secure else resolve_public_addresses(host, port)[0]
    except (OSError, UnicodeError, ValueError) as error:
        raise ProviderError("AI provider unavailable") from error
    path = f"{parts.path.rstrip('/')}/{endpoint.lstrip('/')}".rstrip("/") or "/"
    return Target(host, ip, port, path, secure)


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    def __init__(self, ip: str):
        self.ip = ip
        self.backend = httpcore.SyncBackend()

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        return self.backend.connect_tcp(self.ip, port, timeout, local_address, socket_options)

    def connect_unix_socket(self, path, timeout=None, socket_options=None):
        return self.backend.connect_unix_socket(path, timeout, socket_options)

    def sleep(self, seconds: float) -> None:
        self.backend.sleep(seconds)


class _PinnedHTTPTransport(httpx.HTTPTransport):
    def __init__(self, target: Target):
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=20)
        super().__init__(verify=target.secure, trust_env=False, limits=limits, retries=0)
        ssl_context = self._pool._ssl_context if target.secure else None
        self._pool.close()
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl_context, max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry, http1=True, http2=False, retries=0,
            network_backend=_PinnedNetworkBackend(target.ip),
        )


class _GuardedStream(httpx.SyncByteStream):
    def __init__(self, stream, limit: int):
        self.stream, self.limit, self.total = stream, limit, 0

    def __iter__(self):
        for part in self.stream:
            self.total += len(part)
            if self.total > self.limit:
                raise ProviderError("AI provider unavailable")
            yield part

    def close(self) -> None:
        self.stream.close()


class _GuardedTransport(httpx.BaseTransport):
    def __init__(self, transport):
        self.transport = transport

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self.transport.handle_request(request)
        stream = _GuardedStream(response.stream, MAX_MODELS_BYTES)
        return httpx.Response(
            response.status_code, headers=response.headers, stream=stream,
            extensions=response.extensions, request=request,
        )

    def close(self) -> None:
        self.transport.close()


def _transport(target: Target, _timeout: float, _secure: bool = True):
    return _PinnedHTTPTransport(target)


def _model_ids(payload: dict) -> list[str]:
    values = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(values, list) or len(values) > MAX_MODELS:
        raise ProviderError("AI provider unavailable")
    raw_ids = [item.get("id") for item in values if isinstance(item, dict)]
    if len(raw_ids) != len(values) or not all(isinstance(value, str) for value in raw_ids):
        raise ProviderError("AI provider unavailable")
    ids = [value.strip() for value in raw_ids]
    if any(not value or len(value) > 200 for value in ids):
        raise ProviderError("AI provider unavailable")
    return list(dict.fromkeys(ids))


class OpenAIModelDiscovery:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: int, allow_internal: bool = False):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout_seconds
        self.allow_internal = allow_internal

    def _openai(self) -> OpenAI:
        target = _target(self.base_url, "", self.allow_internal)
        transport = _GuardedTransport(_transport(target, self.timeout, target.secure))
        client = httpx.Client(
            transport=transport, timeout=self.timeout, follow_redirects=False, trust_env=False,
        )
        return OpenAI(
            base_url=self.base_url, api_key=self.api_key, http_client=client,
            timeout=self.timeout, max_retries=0,
        )

    def models(self) -> list[str]:
        client = None
        try:
            client = self._openai()
            page = client.models.list()
            payload = {"data": [{"id": getattr(row, "id", None)} for row in page.data]}
            return _model_ids(payload)
        except Exception as error:
            raise ProviderError("AI provider unavailable") from error
        finally:
            if client is not None:
                client.close()


@asynccontextmanager
async def open_model(selection, allow_internal: bool) -> AsyncIterator[OpenAIChatModel]:
    client = httpx2.AsyncClient(
        transport=RestrictedProviderTransport(
            selection.base_url, selection.timeout_seconds, allow_internal
        ),
        follow_redirects=False, timeout=selection.timeout_seconds, trust_env=False,
    )
    try:
        provider = OpenAIProvider(
            base_url=selection.base_url, api_key=selection.api_key, http_client=client
        )
        yield OpenAIChatModel(selection.model, provider=provider)
    finally:
        await client.aclose()
