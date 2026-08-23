from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import urllib3


@dataclass(frozen=True, slots=True)
class CatalogHealth:
    available: bool
    primary_key: str | None
    generation: str | None
    index_epoch: str | None


@dataclass(frozen=True, slots=True)
class SearchSnapshot:
    response: dict
    index_epoch: str | None


def _secret(path: str) -> str:
    value = Path(path).read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("Meilisearch API Key 为空")
    return value


def create_client(url: str, key_file: str):
    if not url.strip() or not key_file.strip():
        raise RuntimeError("Meilisearch 配置不完整")
    import meilisearch

    return meilisearch.Client(url.strip(), _secret(key_file), timeout=5)


class MeilisearchReader:
    def __init__(self, url: str, key: str) -> None:
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {key}"}
        timeout = urllib3.Timeout(connect=2, read=5)
        self._pool = urllib3.PoolManager(
            maxsize=40,
            block=True,
            timeout=timeout,
            retries=False,
        )

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        headers = self._headers | ({"Content-Type": "application/json"} if body else {})
        payload = json.dumps(body).encode() if body else None
        response = self._pool.request(
            method, f"{self._url}/{path}", headers=headers, body=payload
        )
        if not 200 <= response.status < 300:
            raise RuntimeError(f"Meilisearch HTTP {response.status}")
        value = json.loads(response.data)
        if not isinstance(value, dict):
            raise RuntimeError("Meilisearch 返回格式无效")
        return value

    def _index(self, index_uid: str) -> dict:
        return self._request("GET", f"indexes/{quote(index_uid, safe='')}")

    def health(self, index_uid: str) -> CatalogHealth:
        uid = quote(index_uid, safe="")
        server = self._request("GET", "health")
        index = self._index(index_uid)
        meta = self._request("GET", f"indexes/{uid}/documents/catalog-meta")
        return CatalogHealth(
            server.get("status") == "available",
            index.get("primaryKey"),
            meta.get("generation"),
            index.get("updatedAt"),
        )

    def search(self, index_uid: str, queries: list[dict]) -> SearchSnapshot:
        response = self._request("POST", "multi-search", {"queries": queries})
        return SearchSnapshot(response, self._index(index_uid).get("updatedAt"))


def create_reader(url: str, key_file: str) -> MeilisearchReader:
    if not url.strip() or not key_file.strip():
        raise RuntimeError("Meilisearch 配置不完整")
    return MeilisearchReader(url.strip(), _secret(key_file))


def _task_uid(task) -> int:
    if isinstance(task, dict):
        value = task.get("taskUid", task.get("task_uid", task.get("uid")))
    else:
        value = getattr(task, "task_uid", getattr(task, "uid", None))
    if value is None:
        raise RuntimeError("Meilisearch 未返回任务编号")
    return int(value)


def _task_value(task, name: str):
    return task.get(name) if isinstance(task, dict) else getattr(task, name, None)


def _task_error(task) -> str:
    error = _task_value(task, "error")
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(error or "Meilisearch 任务失败")


def wait_task(client, task) -> None:
    completed = client.wait_for_task(_task_uid(task), timeout_in_ms=25_000)
    if _task_value(completed, "status") != "succeeded":
        raise RuntimeError(_task_error(completed))


def index_epoch(client, index_uid: str) -> str:
    raw = client.get_raw_index(index_uid)
    epoch = raw.get("updatedAt") if isinstance(raw, dict) else None
    if not isinstance(epoch, str) or not epoch:
        raise RuntimeError("Meilisearch 索引缺少更新时间")
    return epoch
