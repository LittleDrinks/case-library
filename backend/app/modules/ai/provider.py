from __future__ import annotations

from asyncio import CancelledError
import ipaddress
import json
import socket
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import SplitResult, urlsplit

import httpcore
import httpx
from openai import OpenAI

MAX_MODELS = 200
MAX_MODELS_BYTES = 1024 * 1024
MAX_CHAT_BYTES = 512 * 1024


class ProviderError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Target:
    host: str
    ip: str
    port: int
    path: str


def _public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    mapped = getattr(address, "ipv4_mapped", None)
    return address.is_global and (mapped is None or mapped.is_global)


def _addresses(host: str, port: int) -> tuple[str, ...]:
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = tuple(dict.fromkeys(record[4][0] for record in records))
    except (OSError, UnicodeError) as error:
        raise ProviderError("AI provider unavailable") from error
    if not addresses or not all(_public_ip(value) for value in addresses):
        raise ProviderError("AI provider unavailable")
    return addresses


def _url_parts(base_url: str, allow_internal: bool = False) -> SplitResult:
    try:
        parts = urlsplit(base_url)
        valid = (
            parts.scheme == ("http" if allow_internal else "https") and parts.hostname
        )
        valid = valid and not parts.username and not parts.password
        valid = valid and not parts.query and not parts.fragment
        if not valid:
            raise ValueError
        parts.port
        return parts
    except ValueError as error:
        raise ProviderError("AI provider unavailable") from error


def _target(base_url: str, endpoint: str, allow_internal: bool = False) -> Target:
    parts = _url_parts(base_url, allow_internal)
    host = parts.hostname.encode("idna").decode("ascii")
    port = parts.port or (80 if allow_internal else 443)
    path = f"{parts.path.rstrip('/')}/{endpoint.lstrip('/')}".rstrip("/") or "/"
    ip = socket.gethostbyname(host) if allow_internal else _addresses(host, port)[0]
    return Target(host, ip, port, path)


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    def __init__(self, ip: str):
        self.ip = ip
        self.backend = httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable | None = None,
    ):
        return self.backend.connect_tcp(
            self.ip, port, timeout, local_address, socket_options
        )

    def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Iterable | None = None
    ):
        return self.backend.connect_unix_socket(path, timeout, socket_options)

    def sleep(self, seconds: float) -> None:
        self.backend.sleep(seconds)


class _PinnedHTTPTransport(httpx.HTTPTransport):
    def __init__(self, target: Target):
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=20)
        super().__init__(verify=True, trust_env=False, limits=limits, retries=0)
        ssl_context = self._pool._ssl_context
        self._pool.close()
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl_context,
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            http1=True,
            http2=False,
            retries=0,
            network_backend=_PinnedNetworkBackend(target.ip),
        )


class _GuardedStream(httpx.SyncByteStream):
    def __init__(self, stream, limit: int, require_done: bool):
        self.stream, self.limit, self.require_done = stream, limit, require_done
        self.total, self.tail, self.done = 0, b"", False

    def __iter__(self):
        for part in self.stream:
            self.total += len(part)
            if self.total > self.limit:
                raise ProviderError("AI provider unavailable")
            if self.require_done:
                self.tail = (self.tail + part)[-32:]
                self.done = self.done or b"data: [DONE]" in self.tail
            yield part
        if self.require_done and not self.done:
            raise ProviderError("AI provider unavailable")

    def close(self) -> None:
        self.stream.close()


class _GuardedTransport(httpx.BaseTransport):
    def __init__(self, transport):
        self.transport = transport

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self.transport.handle_request(request)
        is_chat = request.url.path.rstrip("/").endswith("/chat/completions")
        streaming = is_chat and _is_stream_request(request)
        limit = MAX_CHAT_BYTES if is_chat else MAX_MODELS_BYTES
        stream = _GuardedStream(response.stream, limit, streaming)
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            stream=stream,
            extensions=response.extensions,
            request=request,
        )

    def close(self) -> None:
        self.transport.close()


def _transport(target: Target, _timeout: float, _secure: bool = True):
    return _PinnedHTTPTransport(target)


def _is_stream_request(request: httpx.Request) -> bool:
    try:
        return json.loads(request.content or b"{}").get("stream") is True
    except (TypeError, ValueError):
        return False


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


def _chunk_text(chunk) -> str | None:
    choices = getattr(chunk, "choices", [])
    if not choices:
        return None
    text = getattr(getattr(choices[0], "delta", None), "content", None)
    return text if isinstance(text, str) else None


def _close_client(client) -> None:
    if client is None:
        return
    try:
        client.close()
    except Exception:
        pass


def _close_stream(stream) -> None:
    if stream is None:
        return
    try:
        stream.close()
    except Exception:
        pass


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_seconds: int,
        allow_internal: bool = False,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout_seconds
        self.allow_internal = allow_internal

    def _openai(self) -> OpenAI:
        target = _target(self.base_url, "", self.allow_internal)
        transport = _transport(target, self.timeout, not self.allow_internal)
        transport = _GuardedTransport(transport)
        client = httpx.Client(
            transport=transport,
            timeout=self.timeout,
            follow_redirects=False,
            trust_env=False,
        )
        return OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            http_client=client,
            timeout=self.timeout,
            max_retries=0,
        )

    def chat(self, messages: list[dict], model: str):
        client = stream = None
        try:
            client = self._openai()
            stream = client.chat.completions.create(
                model=model, messages=messages, stream=True
            )
            for chunk in stream:
                text = _chunk_text(chunk)
                if text:
                    yield text
        except (Exception, CancelledError) as error:
            raise ProviderError("AI provider unavailable") from error
        finally:
            _close_stream(stream)
            _close_client(client)

    def structured(self, messages: list[dict], model: str, response_model):
        client = None
        try:
            client = self._openai()
            response = client.beta.chat.completions.parse(
                model=model, messages=messages, response_format=response_model
            )
            parsed = response.choices[0].message.parsed
            if parsed is None:
                raise ValueError("missing structured response")
            return response_model.model_validate(parsed)
        except (Exception, CancelledError) as error:
            raise ProviderError("AI provider unavailable") from error
        finally:
            _close_client(client)

    def models(self) -> list[str]:
        client = None
        try:
            client = self._openai()
            page = client.models.list()
            payload = {"data": [{"id": getattr(row, "id", None)} for row in page.data]}
            return _model_ids(payload)
        except (Exception, CancelledError) as error:
            raise ProviderError("AI provider unavailable") from error
        finally:
            _close_client(client)
