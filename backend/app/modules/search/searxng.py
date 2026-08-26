from __future__ import annotations

import json
from enum import Enum
from typing import TYPE_CHECKING
from urllib.parse import urlencode, urlsplit

import urllib3
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.core.config import Settings

MAX_QUERY_LENGTH = 2_000
MAX_TITLE_LENGTH = 500
MAX_URL_LENGTH = 2_048
MAX_SNIPPET_LENGTH = 2_000
FAILURE_MESSAGE = "联网检索服务不可用，请稍后重试"
TIMEOUT_MESSAGE = "联网检索超时，请稍后重试"
EMPTY_MESSAGE = "未找到联网检索结果"
INVALID_QUERY_MESSAGE = "联网检索关键词不能为空"
INVALID_QUERY_LENGTH_MESSAGE = "联网检索关键词过长"
UNCONFIGURED_MESSAGE = "联网检索服务未配置"


class WebSearchStatus(str, Enum):
    SUCCESS = "success"
    EMPTY = "empty"
    TIMEOUT = "timeout"
    FAILURE = "failure"


class WebSearchItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    url: str
    snippet: str = ""


class WebSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: WebSearchStatus
    items: list[WebSearchItem] = Field(default_factory=list)
    message: str | None = None

    @property
    def results(self) -> list[WebSearchItem]:
        return self.items


SearchStatus = WebSearchStatus
SearchItem = WebSearchItem
SearchResult = WebSearchResult


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _http_url(value: object) -> str | None:
    value = _text(value)
    if not value or len(value) > MAX_URL_LENGTH:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _item(value: object) -> WebSearchItem | None:
    if not isinstance(value, dict):
        return None
    url = _http_url(value.get("url"))
    if not url:
        return None
    title = _text(value.get("title")) or url
    snippet = _text(value.get("content")) or _text(value.get("snippet"))
    return WebSearchItem(
        title=title[:MAX_TITLE_LENGTH],
        url=url,
        snippet=snippet[:MAX_SNIPPET_LENGTH],
    )


def _items(payload: dict, limit: int) -> list[WebSearchItem]:
    values = payload.get("results")
    if not isinstance(values, list):
        raise ValueError("SearXNG 返回格式无效")
    return [item for value in values if (item := _item(value))][:limit]


def _result(
    status: WebSearchStatus,
    items: list[WebSearchItem] | None = None,
    message: str | None = None,
) -> WebSearchResult:
    return WebSearchResult(status=status, items=items or [], message=message)


def _failure(message: str = FAILURE_MESSAGE) -> WebSearchResult:
    return _result(WebSearchStatus.FAILURE, message=message)


def _timeout() -> WebSearchResult:
    return _result(WebSearchStatus.TIMEOUT, message=TIMEOUT_MESSAGE)


def _valid_base_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _pool(timeout_seconds: float):
    timeout = urllib3.Timeout(connect=min(2.0, timeout_seconds), read=timeout_seconds)
    return urllib3.PoolManager(
        maxsize=20,
        block=True,
        timeout=timeout,
        retries=False,
    )


def _url(base_url: str, query: str) -> str:
    values = urlencode({"q": query, "format": "json", "pageno": 1})
    return f"{base_url}/search?{values}"


def _payload(response) -> dict:
    payload = json.loads(response.data)
    if not isinstance(payload, dict):
        raise ValueError("SearXNG 返回格式无效")
    return payload


_TIMEOUT_ERRORS = (TimeoutError, urllib3.exceptions.TimeoutError)
_FAILURE_ERRORS = (
    urllib3.exceptions.HTTPError,
    OSError,
    ValueError,
    TypeError,
    UnicodeError,
    AttributeError,
)


class SearXNGClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 5,
        max_results: int = 10,
        pool=None,
    ) -> None:
        if timeout_seconds <= 0 or max_results <= 0:
            raise ValueError("SearXNG 配置必须为正数")
        self._base_url = base_url.strip().rstrip("/")
        self._max_results = max_results
        self._pool = pool if pool is not None else _pool(timeout_seconds)

    def _request(self, query: str):
        return self._pool.request(
            "GET",
            _url(self._base_url, query),
            headers={"Accept": "application/json"},
            redirect=False,
        )

    def _fetch(self, query: str) -> WebSearchResult:
        try:
            response = self._request(query)
            if response.status in {408, 504}:
                return _timeout()
            if not 200 <= response.status < 300:
                return _failure()
            items = _items(_payload(response), self._max_results)
        except _TIMEOUT_ERRORS:
            return _timeout()
        except _FAILURE_ERRORS:
            return _failure()
        return _result(
            WebSearchStatus.SUCCESS if items else WebSearchStatus.EMPTY,
            items,
            None if items else EMPTY_MESSAGE,
        )

    def search(self, query: str) -> WebSearchResult:
        query = query.strip()
        if not query:
            return _failure(INVALID_QUERY_MESSAGE)
        if len(query) > MAX_QUERY_LENGTH:
            return _failure(INVALID_QUERY_LENGTH_MESSAGE)
        if not self._base_url or not _valid_base_url(self._base_url):
            return _failure(UNCONFIGURED_MESSAGE)
        return self._fetch(query)


SearxngClient = SearXNGClient


def create_client(settings: Settings) -> SearXNGClient:
    return SearXNGClient(
        settings.searxng_base_url,
        settings.searxng_timeout_seconds,
        settings.searxng_max_results,
    )
