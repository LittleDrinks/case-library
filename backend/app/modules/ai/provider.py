from __future__ import annotations

import ipaddress
import json
import queue
import socket
import threading
from dataclasses import dataclass
from time import monotonic
from urllib.parse import SplitResult, urlsplit

import urllib3

MAX_MODELS_BYTES = 1024 * 1024
MAX_MODELS = 200
MAX_CHAT_BYTES = 512 * 1024
MAX_SSE_FRAME_BYTES = 64 * 1024
READ_SIZE = 8192


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
    path = f"{parts.path.rstrip('/')}/{endpoint}"
    ip = socket.gethostbyname(host) if allow_internal else _addresses(host, port)[0]
    return Target(host, ip, port, path)


def _host_header(target: Target) -> str:
    host = f"[{target.host}]" if ":" in target.host else target.host
    return host if target.port == 443 else f"{host}:{target.port}"


def _pool(target: Target, timeout: float, secure: bool = True):
    if not secure:
        return urllib3.HTTPConnectionPool(
            target.ip,
            target.port,
            timeout=urllib3.Timeout(total=timeout),
            maxsize=1,
            block=True,
        )
    return urllib3.HTTPSConnectionPool(
        target.ip,
        target.port,
        timeout=urllib3.Timeout(total=timeout, connect=timeout, read=timeout),
        cert_reqs="CERT_REQUIRED",
        assert_hostname=target.host,
        server_hostname=target.host,
        maxsize=1,
        block=True,
    )


def _headers(target: Target, api_key: str) -> dict[str, str]:
    return {
        "Host": _host_header(target),
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _close(response, pool) -> None:
    if response is not None:
        response.close()
        response.release_conn()
    pool.close()


def _offer(output: queue.Queue, item: tuple, stopped: threading.Event) -> None:
    while not stopped.is_set():
        try:
            output.put(item, timeout=0.05)
            return
        except queue.Full:
            continue


def _read_part(response) -> bytes:
    reader = getattr(response, "read1", None) or response.read
    return reader(READ_SIZE)


def _read_worker(response, output: queue.Queue, stopped: threading.Event) -> None:
    try:
        while not stopped.is_set():
            part = _read_part(response)
            _offer(output, (part, None), stopped)
            if not part:
                return
    except Exception as error:
        _offer(output, (None, error), stopped)


def _next_part(output: queue.Queue, deadline: float) -> tuple:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise ProviderError("AI provider unavailable")
    try:
        return output.get(timeout=remaining)
    except queue.Empty as error:
        raise ProviderError("AI provider unavailable") from error


def _reader(response, output: queue.Queue, stopped: threading.Event) -> None:
    worker = threading.Thread(
        target=_read_worker, args=(response, output, stopped), daemon=True
    )
    worker.start()


def _parts(response, deadline: float, byte_limit: int):
    output, stopped = queue.Queue(maxsize=2), threading.Event()
    _reader(response, output, stopped)
    total = 0
    try:
        while True:
            part, error = _next_part(output, deadline)
            if error:
                raise error
            if not part:
                return
            total += len(part)
            if total > byte_limit:
                raise ProviderError("AI provider unavailable")
            yield part
    finally:
        stopped.set()


def _frames(parts):
    buffer = b""
    for part in parts:
        buffer = (buffer + part).replace(b"\r\n", b"\n")
        while b"\n\n" in buffer:
            frame, buffer = buffer.split(b"\n\n", 1)
            if len(frame) > MAX_SSE_FRAME_BYTES:
                raise ProviderError("AI provider unavailable")
            yield frame
        if len(buffer) > MAX_SSE_FRAME_BYTES:
            raise ProviderError("AI provider unavailable")
    if buffer.strip():
        yield buffer


def _frame_data(frame: bytes) -> str | None:
    try:
        lines = frame.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise ProviderError("AI provider unavailable") from error
    values = [line[5:].lstrip() for line in lines if line.startswith("data:")]
    return "\n".join(values) if values else None


def _chat_tokens(response, deadline: float):
    completed = False
    for frame in _frames(_parts(response, deadline, MAX_CHAT_BYTES)):
        data = _frame_data(frame)
        if data == "[DONE]":
            completed = True
            break
        token = _token(data)
        if token:
            yield token
    if not completed:
        raise ProviderError("AI provider unavailable")


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

    def _request(self, endpoint: str, body: dict | None = None):
        target = _target(self.base_url, endpoint, self.allow_internal)
        pool = _pool(target, self.timeout, not self.allow_internal)
        method = "POST" if body is not None else "GET"
        response = pool.request(
            method,
            target.path,
            headers=_headers(target, self.api_key),
            json=body,
            retries=False,
            redirect=False,
            preload_content=False,
        )
        return response, pool

    def chat(self, messages: list[dict], model: str):
        response = pool = None
        deadline = monotonic() + self.timeout
        try:
            body = {"model": model, "messages": messages, "stream": True}
            response, pool = self._request("chat/completions", body)
            if response.status != 200:
                raise ProviderError("AI provider unavailable")
            yield from _chat_tokens(response, deadline)
        except (urllib3.exceptions.HTTPError, OSError, ValueError, UnicodeError):
            raise ProviderError("AI provider unavailable") from None
        finally:
            if pool is not None:
                _close(response, pool)

    def models(self) -> list[str]:
        response = pool = None
        deadline = monotonic() + self.timeout
        try:
            response, pool = self._request("models")
            return _read_models(response, deadline)
        except (urllib3.exceptions.HTTPError, OSError, ValueError, UnicodeError):
            raise ProviderError("AI provider unavailable") from None
        finally:
            if pool is not None:
                _close(response, pool)


def _read_models(response, deadline: float) -> list[str]:
    content_type = response.headers.get("content-type", "").lower()
    if response.status != 200 or "application/json" not in content_type:
        raise ProviderError("AI provider unavailable")
    payload = b"".join(_parts(response, deadline, MAX_MODELS_BYTES))
    return _model_ids(json.loads(payload))


def _model_ids(payload: dict) -> list[str]:
    values = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(values, list) or len(values) > MAX_MODELS:
        raise ProviderError("AI provider unavailable")
    raw_ids = [item.get("id") for item in values if isinstance(item, dict)]
    if len(raw_ids) != len(values) or not all(
        isinstance(value, str) for value in raw_ids
    ):
        raise ProviderError("AI provider unavailable")
    ids = [value.strip() for value in raw_ids]
    if any(not value or len(value) > 200 for value in ids):
        raise ProviderError("AI provider unavailable")
    return list(dict.fromkeys(ids))


def _token(data: str | None) -> str | None:
    if not data:
        return None
    chunk = json.loads(data)
    choices = chunk.get("choices") or []
    return choices[0].get("delta", {}).get("content") if choices else None
