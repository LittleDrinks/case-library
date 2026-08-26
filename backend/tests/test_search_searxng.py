from __future__ import annotations

import json
from pathlib import Path

import pytest
import urllib3

from app.core.config import Settings
from app.modules.search.searxng import SearXNGClient, WebSearchStatus

FIXTURE = Path(__file__).parent / "fixtures" / "searxng" / "search.json"


class FakeResponse:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.data = json.dumps(payload).encode()
        self.status = status


class FakePool:
    def __init__(self, payload: object = None, status: int = 200, error=None) -> None:
        self.response = FakeResponse(payload or {}, status)
        self.error = error
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method: str, url: str, **options):
        self.calls.append((method, url, options))
        if self.error:
            raise self.error
        return self.response


def fixture_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_success_maps_fixture_and_caps_candidates() -> None:
    pool = FakePool(fixture_payload())
    client = SearXNGClient("http://searxng:8080", max_results=1, pool=pool)

    result = client.search("思政教学")

    assert result.status is WebSearchStatus.SUCCESS
    assert len(result.items) == 1
    assert result.items[0].title == "高校思政教学案例"
    assert result.items[0].url == "https://example.edu.cn/case"
    assert result.items[0].snippet == "公开网页摘要内容。"
    assert "q=%E6%80%9D%E6%94%BF%E6%95%99%E5%AD%A6" in pool.calls[0][1]
    assert "format=json" in pool.calls[0][1]


def test_empty_response_has_explicit_empty_status() -> None:
    client = SearXNGClient("http://searxng:8080", pool=FakePool({"results": []}))

    result = client.search("没有结果")

    assert result.status is WebSearchStatus.EMPTY
    assert result.items == []
    assert result.message == "未找到联网检索结果"


def test_timeout_is_mapped_without_raising() -> None:
    pool = FakePool(error=urllib3.exceptions.TimeoutError("timed out"))
    client = SearXNGClient("http://searxng:8080", pool=pool)

    result = client.search("超时测试")

    assert result.status is WebSearchStatus.TIMEOUT
    assert result.items == []


@pytest.mark.parametrize(
    "payload,status",
    [({"error": "bad"}, 502), ({"results": "bad"}, 200)],
)
def test_upstream_failure_and_malformed_json_are_failures(payload, status) -> None:
    client = SearXNGClient("http://searxng:8080", pool=FakePool(payload, status))

    result = client.search("失败测试")

    assert result.status is WebSearchStatus.FAILURE
    assert result.items == []


def test_unconfigured_client_does_not_attempt_a_request() -> None:
    pool = FakePool()
    client = SearXNGClient("", pool=pool)

    result = client.search("未配置")

    assert result.status is WebSearchStatus.FAILURE
    assert result.message == "联网检索服务未配置"
    assert pool.calls == []


def test_settings_load_searxng_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://search.internal:8080")
    monkeypatch.setenv("SEARXNG_TIMEOUT_SECONDS", "9")
    monkeypatch.setenv("SEARXNG_MAX_RESULTS", "7")

    settings = Settings.from_environment()

    assert settings.searxng_base_url == "http://search.internal:8080"
    assert settings.searxng_timeout_seconds == 9
    assert settings.searxng_max_results == 7
