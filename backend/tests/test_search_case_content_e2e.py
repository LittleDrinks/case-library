from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import mongomock
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.auth.sessions import COOKIE_NAME, create_session
from app.modules.search.client import create_reader, wait_task
from app.modules.search.indexer import CatalogRebuilder
from app.modules.search.meilisearch import MeilisearchCatalog
from app.modules.search.worker import WorkerHeartbeat
from conftest import MemoryBlobStore, PassthroughSession, ReadyCatalogState

pytestmark = pytest.mark.e2e("MEILI_CONTRACT_URL", "MEILI_CONTRACT_KEY_FILE")


@dataclass(slots=True)
class SearchContext:
    http: TestClient
    database: object


def _document(text: str) -> dict:
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def _attachment(level: str, text: str, name: str | None = None) -> dict:
    return {
        "id": f"att-{level}",
        "caseId": "c-content",
        "name": name or f"附件{level}.txt",
        "mediaType": "text/plain",
        "size": len(text.encode()),
        "accessLevel": level,
        "blobId": f"blob-{level}",
        "searchText": text,
        "createdAt": "2026-08-14",
    }


def _published_version() -> dict:
    attachments = [
        _attachment("public", "公开附件雪松词"),
        _attachment("campus", "校内附件山茶词"),
        _attachment("private", "私密附件海棠词", "私密名称玉兰词.txt"),
    ]
    return {
        "id": "v-content",
        "caseId": "c-content",
        "title": "聚合检索案例",
        "summary": "发布摘要",
        "document": _document("正文白鹭词"),
        "attachments": attachments,
        "metadata": {},
    }


def _seed_database():
    database = mongomock.MongoClient()["case_content_search_e2e"]
    database.client.admin.command = lambda _name: {"ok": 1, "isWritablePrimary": True}
    database.client.start_session = lambda: PassthroughSession()
    database.cases.insert_many([_public_case(), _hidden_case()])
    database.case_versions.insert_many([_published_version(), _hidden_version()])
    database.users.insert_many(_users())
    return database


def _public_case() -> dict:
    return {
        "id": "c-content",
        "ownerId": "u-owner",
        "publicationStatus": "public",
        "publishedVersionId": "v-content",
        "publishedAt": "2026-08-14",
    }


def _hidden_case() -> dict:
    return {
        "id": "c-hidden",
        "ownerId": "u-owner",
        "publicationStatus": "hidden",
        "publishedVersionId": "v-hidden",
        "publishedAt": "2026-08-14",
    }


def _hidden_version() -> dict:
    return {
        "id": "v-hidden",
        "caseId": "c-hidden",
        "title": "隐藏案例",
        "summary": "",
        "document": _document("隐藏朱鹮词"),
        "attachments": [],
        "metadata": {},
    }


def _users() -> list[dict]:
    return [
        {
            "id": "u-owner",
            "username": "owner",
            "role": "user",
            "status": "active",
            "token_version": 0,
            "must_change_password": False,
        },
        {
            "id": "u-other",
            "username": "other",
            "role": "user",
            "status": "active",
            "token_version": 0,
            "must_change_password": False,
        },
        {
            "id": "u-admin",
            "username": "admin",
            "role": "admin",
            "status": "active",
            "token_version": 0,
            "must_change_password": False,
        },
    ]


def _meili():
    import meilisearch

    key = (
        Path(os.environ["MEILI_CONTRACT_KEY_FILE"]).read_text(encoding="utf-8").strip()
    )
    return meilisearch.Client(os.environ["MEILI_CONTRACT_URL"], key)


@pytest.fixture(scope="module")
def case_search(tmp_path_factory):
    database, client = _seed_database(), _meili()
    uid = f"case_content_{uuid.uuid4().hex}"
    secret = tmp_path_factory.mktemp("case-search") / "app-secret"
    secret.write_text("case-search-secret", encoding="utf-8")
    settings = Settings(
        app_environment="test", session_cookie_secure=False, app_secret_file=str(secret)
    )
    reader = create_reader(
        os.environ["MEILI_CONTRACT_URL"],
        os.environ["MEILI_CONTRACT_KEY_FILE"],
    )
    catalog = MeilisearchCatalog(reader)
    state = ReadyCatalogState(database)
    app = create_app(database, settings, MemoryBlobStore(), catalog, state)
    with TestClient(app) as http:
        CatalogRebuilder(database, client, uid).rebuild()
        WorkerHeartbeat(database, "case-content-fixture").pulse()
        yield SearchContext(http, database)
    marker = database.search_catalog_generation.find_one({"_id": "catalog"})
    wait_task(client, client.delete_index(marker["indexUid"]))


def _search(
    context: SearchContext, query: str, user_id: str | None = None
) -> list[dict]:
    context.http.cookies.clear()
    if user_id:
        user = context.database.users.find_one({"id": user_id})
        token, _session = create_session(context.database, user, 3600)
        context.http.cookies.set(COOKIE_NAME, token)
    WorkerHeartbeat(context.database, "case-content-fixture").pulse()
    response = context.http.get("/api/search", params={"q": query, "kind": "case"})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _assert_case(items: list[dict]) -> None:
    assert [(item["id"], item["kind"]) for item in items] == [("c-content", "case")]


def test_http_search_finds_published_case_body_as_one_case(case_search) -> None:
    _assert_case(_search(case_search, "正文白鹭词"))


def test_http_search_finds_public_attachment_as_its_case(case_search) -> None:
    _assert_case(_search(case_search, "公开附件雪松词"))


def test_http_search_limits_campus_attachment_to_signed_in_users(case_search) -> None:
    assert _search(case_search, "校内附件山茶词") == []
    _assert_case(_search(case_search, "校内附件山茶词", "u-other"))


def test_http_search_limits_private_attachment_to_owner_and_admin(case_search) -> None:
    assert _search(case_search, "私密附件海棠词") == []
    assert _search(case_search, "私密附件海棠词", "u-other") == []
    _assert_case(_search(case_search, "私密附件海棠词", "u-owner"))
    _assert_case(_search(case_search, "私密附件海棠词", "u-admin"))


def test_http_search_exposes_attachment_names_as_public_metadata(case_search) -> None:
    _assert_case(_search(case_search, "私密名称玉兰词"))
    assert _search(case_search, "私密附件海棠词") == []


def test_http_search_never_finds_hidden_case_content(case_search) -> None:
    assert _search(case_search, "隐藏朱鹮词", "u-admin") == []
