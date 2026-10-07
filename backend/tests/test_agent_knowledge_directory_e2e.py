from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from app.core.config import Settings
from app.main import create_app
from app.modules.agent import agent
from app.modules.auth.sessions import COOKIE_NAME
from app.modules.search.client import create_reader, index_epoch, wait_task
from app.modules.search.indexer import catalog_settings
from app.modules.search.meilisearch import MeilisearchCatalog
from app.modules.search.projection import project_catalog_documents
from conftest import MemoryBlobStore
from fastapi.testclient import TestClient
from pydantic_ai.models.function import FunctionModel
from pymongo import MongoClient
from tests.test_agent_visibility import (
    _auth,
    _has_tool_call_id,
    _post_stream,
    _stream_body,
    _thread,
    _tool_delta,
)

pytestmark = pytest.mark.e2e(
    "AUTH_QUERY_MONGODB_URI", "MEILI_CONTRACT_URL", "MEILI_CONTRACT_KEY_FILE"
)

NORMAL_ANSWER = "完成普通创作。"
LEAK_MARK = "不得输出已下线教材正文"
CASE_CAMPUS_MARKER = "issue360campusonlymarker"


def _run_model(
    kind: str | None, call_id: str, answer: str = NORMAL_ANSWER,
) -> FunctionModel:
    async def stream(messages, _info):
        if not _has_tool_call_id(messages, call_id):
            arguments = {"query": ""}
            if kind is not None:
                arguments["kind"] = kind
            yield _tool_delta("search_corpus", arguments, call_id)
            return
        yield answer

    return FunctionModel(stream_function=stream)


def _last_search_sources(database, thread_id: str) -> list[dict]:
    messages = list(database.agent_messages.find(
        {"threadId": thread_id, "role": "assistant"}
    ).sort("messageSeq", -1))
    for message in messages:
        for part in message.get("parts", []):
            if part.get("type") == "tool-search_corpus":
                return part.get("output", {}).get("sources", [])
    raise AssertionError("Agent assistant history has no search_corpus result")


def _last_tool_output(database, thread_id: str, part_type: str) -> dict:
    messages = list(database.agent_messages.find(
        {"threadId": thread_id, "role": "assistant"}
    ).sort("messageSeq", -1))
    for message in messages:
        for part in message.get("parts", []):
            if part.get("type") == part_type:
                return part.get("output", {})
    raise AssertionError(f"Agent assistant history has no {part_type} result")


def _search_then_read_model(
    query: str, source_id: str, search_call: str, read_call: str, answer: str,
) -> FunctionModel:
    async def stream(messages, _info):
        if not _has_tool_call_id(messages, search_call):
            yield _tool_delta(
                "search_corpus", {"query": query, "kind": "knowledge"}, search_call,
            )
            return
        if not _has_tool_call_id(messages, read_call):
            yield _tool_delta(
                "read_source", {"source_type": "knowledge", "source_id": source_id},
                read_call,
            )
            return
        yield answer

    return FunctionModel(stream_function=stream)


def _case_search_model(call_id: str) -> FunctionModel:
    async def stream(messages, _info):
        if not _has_tool_call_id(messages, call_id):
            yield _tool_delta(
                "search_corpus",
                {"query": CASE_CAMPUS_MARKER, "kind": "case"},
                call_id,
            )
            return
        yield NORMAL_ANSWER

    return FunctionModel(stream_function=stream)


def test_real_knowledge_directory_search_rechecks_source_status(tmp_path) -> None:
    from tests.test_search_meilisearch_e2e import _meili_client

    mongo = MongoClient(
        os.environ["AUTH_QUERY_MONGODB_URI"], serverSelectionTimeoutMS=5000
    )
    database_name = f"case_library_e2e_360_knowledge_{uuid.uuid4().hex}"
    database = mongo[database_name]
    meili_admin, key_file = _meili_client()
    uid = f"issue360_knowledge_{uuid.uuid4().hex}"
    created_index = False
    source_id = "ks-360-real-directory"
    source_title = "合成真实教材目录"
    secret = tmp_path / "app-secret"
    secret.write_text("synthetic-test-secret", encoding="utf-8")
    settings = Settings(
        app_environment="test",
        enable_demo_seed=True,
        session_cookie_secure=False,
        app_secret_file=str(secret),
    )
    search_catalog = MeilisearchCatalog(
        create_reader(os.environ["MEILI_CONTRACT_URL"], key_file)
    )
    api = create_app(
        database=database,
        settings=settings,
        blob_store=MemoryBlobStore(),
        search_catalog=search_catalog,
    )

    try:
        wait_task(
            meili_admin,
            meili_admin.create_index(uid, {"primaryKey": "catalogId"}),
        )
        created_index = True
        index = meili_admin.index(uid)
        wait_task(meili_admin, index.update_settings(catalog_settings()))
        source = {
            "id": source_id,
            "title": source_title,
            "edition": "2026版",
            "summary": "合成公开目录摘要",
            "chapterCount": 1,
            "sectionCount": 1,
            "status": "active",
        }
        section = {
            "id": "kn-360-real-directory-section",
            "sourceId": source_id,
            "chapterId": "kc-360-real-directory",
            "chapter": "合成绪论",
            "index": 1,
            "title": "合成有效章节",
            "summary": "合成章节摘要",
            "content": "仅供校验当前知识实体层级的合成正文。",
        }
        documents = [
            *project_catalog_documents("knowledge_source", source),
            *project_catalog_documents("knowledge_section", section),
        ]
        wait_task(meili_admin, index.add_documents(documents))
        epoch = index_epoch(meili_admin, uid)

        with TestClient(api) as client:
            database.knowledge_sources.insert_one(source)
            database.knowledge_sections.insert_one(section)
            database.search_catalog_generation.update_one(
                {"_id": "catalog"},
                {"$set": {
                    "generation": "issue360-real-knowledge",
                    "indexUid": uid,
                    "indexEpoch": epoch,
                    "retiredIndexUids": [],
                }},
                upsert=True,
            )
            database.search_control.update_one(
                {"_id": "catalog"}, {"$set": {"sequence": 0}}, upsert=True
            )
            database.search_worker_state.update_one(
                {"_id": "catalog"},
                {"$set": {"worker": "issue360-e2e", "updatedAt": datetime.now(UTC)}},
                upsert=True,
            )
            auth = _auth(client)
            thread_id = _thread(client, "c-draft-1")

            for kind, call_id in (("knowledge", "real-empty-knowledge"), (None, "real-empty-all")):
                response = _post_stream(
                    client, auth, "c-draft-1", thread_id,
                    _stream_body("探索教材目录后继续普通创作", f"{call_id}-message"),
                    _run_model(kind, call_id),
                )
                assert response.status_code == 200, response.text
                assert NORMAL_ANSWER in response.text
                [directory] = _last_search_sources(database, thread_id)
                assert directory["id"] == source_id
                assert directory["knowledgeLevel"] == "source"

            section_read = _post_stream(
                client, auth, "c-draft-1", thread_id,
                _stream_body("读取搜索命中的当前章节", "real-section-read"),
                _search_then_read_model(
                    "合成有效章节", section["id"], "real-section-search",
                    "real-section-source-read", "已读到当前章节。",
                ),
            )
            assert section_read.status_code == 200, section_read.text
            assert "已读到当前章节。" in section_read.text
            section_sources = _last_search_sources(database, thread_id)
            section_hit = next(item for item in section_sources if item["id"] == section["id"])
            assert section_hit["knowledgeLevel"] == "section"
            assert section_hit["version"] == source["edition"]
            section_output = _last_tool_output(database, thread_id, "tool-read_source")
            assert section_output["status"] == "ok"
            assert section_output["usedSourceRef"]["version"] == source["edition"]
            assert section_output["content"] == section["content"]

            collision_id = "kn-360-directory-section-id-collision"
            collision_source = {
                "id": collision_id,
                "title": "合成重号目录",
                "edition": "2026版",
                "summary": "合成目录摘要",
                "status": "active",
            }
            collision_section = {
                "id": collision_id,
                "sourceId": source_id,
                "chapter": "合成重号章节",
                "title": "不能经目录 ID 读取的章节",
                "content": "directory-id-collision-secret-body",
            }
            database.knowledge_sources.insert_one(collision_source)
            database.knowledge_sections.insert_one(collision_section)
            wait_task(meili_admin, index.add_documents([
                *project_catalog_documents("knowledge_source", collision_source),
                *project_catalog_documents("knowledge_section", collision_section),
            ]))
            collision_read = _post_stream(
                client, auth, "c-draft-1", thread_id,
                _stream_body("读取目录来源", "real-collision-read"),
                _search_then_read_model(
                    collision_source["title"], collision_id, "real-collision-search",
                    "real-collision-source-read", "目录条目不能代替章节正文。",
                ),
            )
            assert collision_read.status_code == 200, collision_read.text
            assert "directory-id-collision-secret-body" not in collision_read.text
            collision_output = _last_tool_output(database, thread_id, "tool-read_source")
            assert collision_output["status"] == "unavailable"
            assert "content" not in collision_output

            database.knowledge_sources.update_one(
                {"id": source_id}, {"$set": {"status": "retired"}}
            )
            offline = _post_stream(
                client, auth, "c-draft-1", thread_id,
                _stream_body("目录下线后继续创作", "real-retired-source-message"),
                _run_model("knowledge", "real-retired-source", LEAK_MARK),
            )
            assert offline.status_code == 200, offline.text
            assert NORMAL_ANSWER not in offline.text
            assert LEAK_MARK not in offline.text
            assert source_id not in offline.text
            latest_run = database.agent_runs.find_one(
                {"threadId": thread_id}, sort=[("startedAt", -1)]
            )
            assert latest_run["status"] == "cancelled"
    finally:
        if created_index:
            wait_task(meili_admin, meili_admin.delete_index(uid))
        mongo.drop_database(database_name)
        mongo.close()


def test_real_case_search_http_and_agent_use_current_campus_grant(tmp_path) -> None:
    from tests.test_search_meilisearch_e2e import _meili_client

    mongo = MongoClient(
        os.environ["AUTH_QUERY_MONGODB_URI"], serverSelectionTimeoutMS=5000
    )
    database_name = f"case_library_e2e_360_case_{uuid.uuid4().hex}"
    database = mongo[database_name]
    meili_admin, key_file = _meili_client()
    uid = f"issue360_case_{uuid.uuid4().hex}"
    created_index = False
    secret = tmp_path / "app-secret"
    secret.write_text("synthetic-test-secret", encoding="utf-8")
    settings = Settings(
        app_environment="test",
        enable_demo_seed=True,
        session_cookie_secure=False,
        app_secret_file=str(secret),
    )
    catalog = MeilisearchCatalog(
        create_reader(os.environ["MEILI_CONTRACT_URL"], key_file)
    )
    api = create_app(
        database=database,
        settings=settings,
        blob_store=MemoryBlobStore(),
        search_catalog=catalog,
    )

    try:
        wait_task(
            meili_admin,
            meili_admin.create_index(uid, {"primaryKey": "catalogId"}),
        )
        created_index = True
        index = meili_admin.index(uid)
        wait_task(meili_admin, index.update_settings(catalog_settings()))
        version = {
            "id": "v-360-campus-search",
            "number": 1,
            "caseId": "c-360-campus-search",
            "title": "合成公开案例",
            "summary": "仅含公开摘要",
            "document": {"type": "doc", "content": []},
            "attachments": [{
                "id": "att-360-campus-search",
                "name": "合成校内附件.txt",
                "accessLevel": "campus",
                "searchText": CASE_CAMPUS_MARKER,
            }],
            "metadata": {},
        }
        documents = project_catalog_documents(
            "case", version,
            {"publishedAt": "2026-10-08", "ownerId": "u-360-other-owner"},
        )
        wait_task(meili_admin, index.add_documents(documents))
        epoch = index_epoch(meili_admin, uid)

        with TestClient(api) as client:
            database.search_catalog_generation.update_one(
                {"_id": "catalog"},
                {"$set": {
                    "generation": "issue360-real-case-search",
                    "indexUid": uid,
                    "indexEpoch": epoch,
                    "retiredIndexUids": [],
                }},
                upsert=True,
            )
            database.search_control.update_one(
                {"_id": "catalog"}, {"$set": {"sequence": 0}}, upsert=True
            )
            database.search_worker_state.update_one(
                {"_id": "catalog"},
                {"$set": {
                    "worker": "issue360-e2e",
                    "updatedAt": datetime.now(UTC),
                }},
                upsert=True,
            )

            user = database.users.find_one({"username": "user"})
            admin = database.users.find_one({"username": "admin"})
            assert user and admin
            database.users.update_many(
                {"id": {"$in": [user["id"], admin["id"]]}},
                {"$set": {"campus_verified": False}},
            )

            def login(username: str, password: str) -> tuple[dict, str]:
                response = client.post(
                    "/api/auth/login", json={"username": username, "password": password}
                )
                assert response.status_code == 200, response.text
                token = client.cookies.get(COOKIE_NAME)
                assert token
                return response.json(), token

            user_auth, user_token = login("user", "user123")
            admin_auth, admin_token = login("admin", "admin123")
            assert user_auth["user"]["id"] == user["id"]
            assert admin_auth["user"]["id"] == admin["id"]

            def search_pair(token: str, expected: bool) -> None:
                client.cookies.clear()
                client.cookies.set(COOKIE_NAME, token)
                get_result = client.get(
                    "/api/search",
                    params={"q": CASE_CAMPUS_MARKER, "kind": "case"},
                )
                post_result = client.post(
                    "/api/search",
                    json={"q": CASE_CAMPUS_MARKER, "kind": "case"},
                )
                assert get_result.status_code == 200, get_result.text
                assert post_result.status_code == 200, post_result.text
                for response in (get_result, post_result):
                    ids = [item["id"] for item in response.json()["items"]]
                    assert ids == (["c-360-campus-search"] if expected else [])
                    assert response.json()["total"] == (1 if expected else 0)
                    assert response.json()["counts"]["case"] == (1 if expected else 0)

            def agent_search(token: str, auth: dict, owner_id: str, call_id: str) -> list[dict]:
                client.cookies.clear()
                client.cookies.set(COOKIE_NAME, token)
                case_id = f"c-360-agent-{call_id}"
                database.cases.insert_one({
                    "id": case_id,
                    "ownerId": owner_id,
                    "publicationStatus": "private",
                    "workflowStatus": "draft",
                    "title": "合成 Agent 草稿",
                    "document": {"type": "doc", "content": []},
                })
                thread_response = client.get(f"/api/cases/{case_id}/agent/thread")
                assert thread_response.status_code == 200, thread_response.text
                thread_id = thread_response.json()["id"]
                with agent.override(model=_case_search_model(call_id)):
                    response = client.post(
                        f"/api/cases/{case_id}/agent/thread/{thread_id}/stream",
                        headers={"X-CSRF-Token": auth["csrfToken"]},
                        json=_stream_body(
                            "检索合成校内附件关键词后继续普通创作",
                            f"{call_id}-message",
                        ),
                    )
                assert response.status_code == 200, response.text
                assert NORMAL_ANSWER in response.text
                return _last_search_sources(database, thread_id)

            search_pair(user_token, expected=False)
            assert agent_search(user_token, user_auth, user["id"], "ordinary") == []
            search_pair(admin_token, expected=False)
            assert agent_search(admin_token, admin_auth, admin["id"], "admin-unverified") == []

            database.users.update_one(
                {"id": admin["id"]}, {"$set": {"campus_verified": True}}
            )
            search_pair(admin_token, expected=True)
            [approved_source] = agent_search(
                admin_token, admin_auth, admin["id"], "admin-approved"
            )
            assert approved_source["id"] == "c-360-campus-search"

            database.users.update_one(
                {"id": admin["id"]}, {"$set": {"campus_verified": False}}
            )
            search_pair(admin_token, expected=False)
            assert agent_search(
                admin_token, admin_auth, admin["id"], "admin-revoked"
            ) == []
    finally:
        if created_index:
            wait_task(meili_admin, meili_admin.delete_index(uid))
        mongo.drop_database(database_name)
        mongo.close()
