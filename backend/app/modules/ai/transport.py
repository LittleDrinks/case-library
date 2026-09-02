from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

import httpx2 as httpx
import urllib3


MAX_REQUEST_BYTES = 512 * 1024
MAX_CHAT_BYTES = 512 * 1024
READ_SIZE = 8192


class ProviderError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Target:
    host: str
    ip: str
    port: int
    path: str
    secure: bool = True


def _public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    mapped = getattr(address, "ipv4_mapped", None)
    return address.is_global and (mapped is None or mapped.is_global)


def resolve_public_addresses(host: str, port: int) -> tuple[str, ...]:
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = tuple(dict.fromkeys(record[4][0] for record in records))
    except (OSError, UnicodeError) as error:
        raise ProviderError("AI provider unavailable") from error
    if not addresses or not all(_public_ip(value) for value in addresses):
        raise ProviderError("AI provider unavailable")
    return addresses


def parse_provider_url(base_url: str, allow_internal: bool = False) -> SplitResult:
    try:
        parts = urlsplit(base_url)
        secure = parts.scheme == "https"
        valid = parts.hostname and (secure or (allow_internal and parts.scheme == "http"))
        valid = valid and not parts.username and not parts.password
        valid = valid and not parts.query and not parts.fragment
        if not valid:
            raise ValueError
        parts.port
        return parts
    except ValueError as error:
        raise ProviderError("AI provider unavailable") from error


def provider_hostname(value: str) -> str:
    try:
        return value.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise ProviderError("AI provider unavailable") from error


def provider_host_header(target: Target) -> str:
    host = f"[{target.host}]" if ":" in target.host else target.host
    default = 443 if target.secure else 80
    return host if target.port == default else f"{host}:{target.port}"


def target_for_url(base_url: str, allow_internal: bool = False) -> Target:
    parts = parse_provider_url(base_url, allow_internal)
    host = provider_hostname(parts.hostname)
    secure = parts.scheme == "https"
    port = parts.port or (443 if secure else 80)
    try:
        ip = socket.gethostbyname(host) if allow_internal and not secure else resolve_public_addresses(host, port)[0]
    except (OSError, UnicodeError, ValueError) as error:
        raise ProviderError("AI provider unavailable") from error
    return Target(host, ip, port, parts.path.rstrip("/") or "/", secure)


def _same_origin(target: Target, request: httpx.Request) -> bool:
    default = 443 if target.secure else 80
    return (
        request.url.scheme == ("https" if target.secure else "http")
        and request.url.host.lower() == target.host.lower()
        and (request.url.port or default) == target.port
    )


def _request_target(target: Target, request: httpx.Request) -> Target:
    if not _same_origin(target, request):
        raise ProviderError("AI provider unavailable")
    if not _path_allowed(target.path, request.url.path):
        raise ProviderError("AI provider unavailable")
    return Target(target.host, target.ip, target.port, request.url.raw_path.decode("ascii"), target.secure)


def _path_allowed(base_path: str, path: str) -> bool:
    root = base_path.rstrip("/")
    return not root or path == base_path or path.startswith(root + "/")


def _request_headers(request: httpx.Request, target: Target) -> dict[str, str]:
    headers = {key: value for key, value in request.headers.items() if key.lower() != "host"}
    headers["Host"] = provider_host_header(target)
    return headers


def _provider_pool(target: Target, timeout: float):
    options = {
        "timeout": urllib3.Timeout(total=timeout, connect=timeout, read=timeout),
        "maxsize": 1,
        "block": True,
    }
    if target.secure:
        return urllib3.HTTPSConnectionPool(
            target.ip, target.port, cert_reqs="CERT_REQUIRED", assert_hostname=target.host,
            server_hostname=target.host, **options
        )
    return urllib3.HTTPConnectionPool(target.ip, target.port, **options)


def _open_response(target, request, body, timeout):
    pool = _provider_pool(target, timeout)
    try:
        response = pool.request(
            request.method, target.path, body=body, headers=_request_headers(request, target),
            retries=False, redirect=False, preload_content=False,
        )
        return response, pool
    except Exception as error:
        pool.close()
        raise ProviderError("AI provider unavailable") from error


def _read(response) -> bytes:
    reader = getattr(response, "read1", None) or response.read
    return reader(READ_SIZE)


def _close_response(response) -> None:
    response.close()
    response.release_conn()


class _ProviderStream(httpx.AsyncByteStream):
    def __init__(self, response, pool, timeout: float, limit: int, deadline: float) -> None:
        self.response = response
        self.pool = pool
        self.timeout = timeout
        self.limit = limit
        self.deadline = deadline
        self.total = 0

    def _remaining(self) -> float:
        return self.deadline - asyncio.get_running_loop().time()

    async def __aiter__(self):
        try:
            while True:
                remaining = self._remaining()
                if remaining <= 0:
                    raise TimeoutError("AI provider stream exceeded the total deadline")
                part = await asyncio.wait_for(asyncio.to_thread(_read, self.response), remaining)
                if not part:
                    break
                self._check_limit(part)
                yield part
        finally:
            await self.aclose()

    def _check_limit(self, part: bytes) -> None:
        self.total += len(part)
        if self.total > self.limit:
            raise ProviderError("AI provider unavailable")

    async def aclose(self) -> None:
        response, pool = self.response, self.pool
        self.response, self.pool = None, None
        if response is not None:
            await asyncio.to_thread(_close_response, response)
        if pool is not None:
            await asyncio.to_thread(pool.close)


class RestrictedProviderTransport(httpx.AsyncBaseTransport):
    def __init__(self, base_url: str, timeout: float, allow_internal: bool = False) -> None:
        self.target = target_for_url(base_url, allow_internal)
        self.timeout = timeout

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        if len(body) > MAX_REQUEST_BYTES:
            raise ProviderError("AI provider unavailable")
        target = _request_target(self.target, request)
        deadline = asyncio.get_running_loop().time() + self.timeout
        response, pool = await asyncio.to_thread(_open_response, target, request, body, self.timeout)
        stream = _ProviderStream(response, pool, self.timeout, MAX_CHAT_BYTES, deadline)
        return httpx.Response(response.status, headers=dict(response.headers), stream=stream, request=request)

    async def aclose(self) -> None:
        return None
