from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from types import SimpleNamespace

import pytest

from app.modules.search.client import create_client, create_reader, wait_task


class FakeClient:
    def __init__(self, url: str, key: str, timeout=None, result=None) -> None:
        self.url = url
        self.key = key
        self.timeout = timeout
        self.result = result or {"status": "succeeded"}
        self.waited = None

    def wait_for_task(self, uid: int, **options):
        self.waited = (uid, options)
        return self.result


class FakeResponse:
    def __init__(self, body: dict, status: int = 200) -> None:
        self.data = json.dumps(body).encode()
        self.status = status


class FakePool:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = [FakeResponse(response) for response in responses]
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method: str, url: str, **options):
        self.calls.append((method, url, options))
        return self.responses.pop(0)


class ConcurrentPool:
    def __init__(self) -> None:
        self.active = self.maximum = 0
        self.lock, self.release = Lock(), Event()

    def request(self, method: str, _url: str, **_options):
        if method == "GET":
            return FakeResponse({"updatedAt": "epoch-1"})
        with self.lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            if self.active == 2:
                self.release.set()
        self.release.wait(0.2)
        with self.lock:
            self.active -= 1
        return FakeResponse({"results": []})


def _reader(tmp_path, monkeypatch, pool):
    secret = tmp_path / "meili-key"
    secret.write_text("secret-key", encoding="utf-8")
    options = {}

    def build_pool(**values):
        options.update(values)
        return pool

    monkeypatch.setattr("urllib3.PoolManager", build_pool)
    return create_reader("http://meilisearch:7700/", str(secret)), options


def _assert_request_headers(pool: FakePool) -> None:
    post_headers = pool.calls[0][2]["headers"]
    get_headers = pool.calls[1][2]["headers"]
    assert json.loads(pool.calls[0][2]["body"]) == {"queries": [{"q": "思政"}]}
    assert post_headers["Content-Type"] == "application/json"
    assert "Content-Type" not in get_headers
    assert get_headers["Authorization"] == "Bearer secret-key"


def test_client_reads_api_key_only_from_secret_file(tmp_path, monkeypatch) -> None:
    secret = tmp_path / "meili-key"
    secret.write_text("  secret-key\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "meilisearch", SimpleNamespace(Client=FakeClient))

    client = create_client("http://meilisearch:7700", str(secret))

    assert (client.url, client.key, client.timeout) == (
        "http://meilisearch:7700",
        "secret-key",
        5,
    )


def test_reader_search_uses_one_pool_and_checks_the_post_search_epoch(
    tmp_path,
    monkeypatch,
) -> None:
    pool = FakePool([{"results": [{"hits": []}]}, {"updatedAt": "epoch-1"}])
    reader, options = _reader(tmp_path, monkeypatch, pool)
    snapshot = reader.search("catalog/current", [{"q": "思政"}])
    assert snapshot.response == {"results": [{"hits": []}]}
    assert snapshot.index_epoch == "epoch-1"
    _assert_search_calls(pool)
    _assert_request_headers(pool)
    _assert_pool_options(options)


def _assert_search_calls(pool: FakePool) -> None:
    calls = [(method, url) for method, url, _options in pool.calls]
    assert calls == [
        ("POST", "http://meilisearch:7700/multi-search"),
        ("GET", "http://meilisearch:7700/indexes/catalog%2Fcurrent"),
    ]


def _assert_pool_options(options: dict) -> None:
    assert (options["maxsize"], options["block"]) == (40, True)
    assert options["retries"] is False
    timeout = options["timeout"]
    assert (timeout.connect_timeout, timeout.read_timeout) == (2, 5)


def test_reader_pool_allows_concurrent_searches(tmp_path, monkeypatch) -> None:
    pool = ConcurrentPool()
    reader, _options = _reader(tmp_path, monkeypatch, pool)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(reader.search, "catalog", []) for _slot in range(2)]
        for future in futures:
            future.result()
    assert pool.maximum == 2


@pytest.mark.parametrize("build", [create_client, create_reader])
@pytest.mark.parametrize("url,key_file", [("", "/secret"), ("http://meili", "")])
def test_client_requires_search_url_and_secret_file(
    build, url: str, key_file: str
) -> None:
    with pytest.raises(RuntimeError, match="Meilisearch 配置不完整"):
        build(url, key_file)


def test_wait_task_accepts_sdk_task_envelopes() -> None:
    client = FakeClient("url", "key")

    wait_task(client, {"taskUid": 17})

    assert client.waited == (17, {"timeout_in_ms": 25_000})


def test_wait_task_rejects_a_failed_asynchronous_write() -> None:
    result = {"status": "failed", "error": {"message": "index write failed"}}
    client = FakeClient("url", "key", result=result)

    with pytest.raises(RuntimeError, match="index write failed"):
        wait_task(client, SimpleNamespace(task_uid=18))
