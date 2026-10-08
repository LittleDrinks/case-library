from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime
from dataclasses import replace
from io import BytesIO
from threading import Event
from concurrent.futures import ThreadPoolExecutor

import pytest
from app.core.config import Settings
from app.main import create_app
from app.modules.agent import agent
from app.modules.agent.prosemirror import text_blocks
from app.modules.attachments.storage import minio_blob_store
from app.modules.auth.sessions import COOKIE_NAME
from app.modules.search.client import create_reader, index_epoch, wait_task
from app.modules.search.indexer import catalog_settings
from app.modules.search.meilisearch import MeilisearchCatalog
from app.modules.search.projection import PROJECTION_VERSION, project_catalog_documents
from app.modules.search.state import MongoCatalogState
from fastapi.testclient import TestClient
from pydantic_ai.models.function import FunctionModel
from pymongo import MongoClient
from tests.test_agent_visibility import (
    _auth,
    _history_texts,
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
CASE_CAMPUS_MARKER = "issue360campusonlymarker"


def _real_storage_settings(tmp_path, prefix: str):
    secret = tmp_path / f"{prefix}-app-secret"
    secret.write_text("synthetic-test-secret", encoding="utf-8")
    bucket = f"case-library-360-{prefix}-{uuid.uuid4().hex}"
    settings = replace(
        Settings(),
        app_environment="test",
        enable_demo_seed=True,
        session_cookie_secure=False,
        app_secret_file=str(secret),
        object_store_endpoint=os.environ["OBJECT_STORE_ENDPOINT"],
        object_store_bucket=bucket,
        object_store_access_key_file=os.environ["OBJECT_STORE_ACCESS_KEY_FILE"],
        object_store_secret_key_file=os.environ["OBJECT_STORE_SECRET_KEY_FILE"],
    )
    return settings, minio_blob_store(settings), bucket


def _cleanup_bucket(store, bucket: str) -> None:
    if not store.client.bucket_exists(bucket):
        return
    for item in store.client.list_objects(bucket, recursive=True):
        store.client.remove_object(bucket, item.object_name)
    store.client.remove_bucket(bucket)


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


def _last_search_sources(
    database, thread_id: str, run_id: str | None = None,
) -> list[dict]:
    query = {"threadId": thread_id, "role": "assistant"}
    if run_id:
        query["runId"] = run_id
    messages = list(database.agent_messages.find(query).sort("messageSeq", -1))
    for message in messages:
        for part in message.get("parts", []):
            if part.get("type") == "tool-search_corpus":
                return part.get("output", {}).get("sources", [])
    raise AssertionError("Agent assistant history has no search_corpus result")


def _last_tool_output(
    database, thread_id: str, part_type: str, run_id: str | None = None,
) -> dict:
    query = {"threadId": thread_id, "role": "assistant"}
    if run_id:
        query["runId"] = run_id
    messages = list(database.agent_messages.find(query).sort("messageSeq", -1))
    for message in messages:
        for part in message.get("parts", []):
            if part.get("type") == part_type:
                return part.get("output", {})
    raise AssertionError(f"Agent assistant history has no {part_type} result")


def _set_catalog_health(database, generation: str, index_uid: str, epoch: str) -> None:
    database.search_catalog_generation.update_one(
        {"_id": "catalog"},
        {"$set": {
            "generation": generation,
            "indexUid": index_uid,
            "indexEpoch": epoch,
            "projectionVersion": PROJECTION_VERSION,
            "retiredIndexUids": [],
        }},
        upsert=True,
    )
    database.search_worker_state.update_one(
        {"_id": "catalog"},
        {"$set": {
            "worker": "issue360-e2e",
            "updatedAt": datetime.now(UTC),
            "status": "healthy",
            "indexUid": index_uid,
            "indexEpoch": epoch,
        }},
        upsert=True,
    )


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


def _three_turn_title_model(title: str) -> FunctionModel:
    async def stream(messages, _info):
        if not _has_tool_call_id(messages, "three-turn-title-search"):
            yield _tool_delta(
                "search_corpus", {"query": title, "kind": "material"},
                "three-turn-title-search",
            )
            return
        yield f"根据公开目录标题继续普通创作：{title}。"

    return FunctionModel(stream_function=stream)


def _three_turn_range_model(title: str, material_id: str, range_target: dict,
                            body_marker: str) -> FunctionModel:
    async def stream(messages, _info):
        if not _has_tool_call_id(messages, "three-turn-body-search"):
            yield _tool_delta(
                "search_corpus", {"query": title, "kind": "material"},
                "three-turn-body-search",
            )
            return
        if not _has_tool_call_id(messages, "three-turn-body-read"):
            yield _tool_delta(
                "read_source",
                {"source_type": "material", "source_id": material_id},
                "three-turn-body-read",
            )
            return
        if not _has_tool_call_id(messages, "three-turn-range-artifact"):
            yield _tool_delta(
                "propose_revision",
                {
                    "start": range_target["start"],
                    "end": range_target["end"],
                    "replacement": "撤销后不得应用的范围修订",
                    "reason": "合成范围候选理由",
                },
                "three-turn-range-artifact",
            )
            return
        yield f"第二轮实际读取正文：{body_marker}。"

    return FunctionModel(stream_function=stream)


def _three_turn_document_model(title: str, material_id: str) -> FunctionModel:
    async def stream(messages, _info):
        if not _has_tool_call_id(messages, "three-turn-document-search"):
            yield _tool_delta(
                "search_corpus", {"query": title, "kind": "material"},
                "three-turn-document-search",
            )
            return
        if not _has_tool_call_id(messages, "three-turn-document-read"):
            yield _tool_delta(
                "read_source",
                {"source_type": "material", "source_id": material_id},
                "three-turn-document-read",
            )
            return
        if not _has_tool_call_id(messages, "three-turn-document-artifact"):
            yield _tool_delta(
                "propose_document",
                {
                    "blocks": [{
                        "type": "paragraph",
                        "text": "撤销后不得采纳的整篇候选",
                    }],
                    "reason": "合成整篇候选理由",
                },
                "three-turn-document-artifact",
            )
            return
        yield "已创建整篇候选。"

    return FunctionModel(stream_function=stream)


def _three_turn_history_model(
    body_marker: str, emitted_text: str, entered: Event, resume: Event,
    emitted_calls: Event,
) -> FunctionModel:
    async def stream(messages, _info):
        assert body_marker in _history_texts([messages])
        entered.set()
        if not await asyncio.to_thread(resume.wait, 30):
            raise TimeoutError("第三轮测试模型未收到恢复信号")
        proposal = _tool_delta(
            "propose_document",
            {
                "blocks": [{"type": "paragraph", "text": emitted_text}],
                "reason": "撤销后不得建立整篇版本",
            },
            "three-turn-propose-after-revoke",
        )[0]
        direct_write = _tool_delta(
            "write_document",
            {
                "blocks": [{"type": "paragraph", "text": emitted_text}],
                "summary": "撤销后不得直接写入",
            },
            "three-turn-write-after-revoke",
        )[0]
        emitted_calls.set()
        yield {0: proposal, 1: direct_write}

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
    settings, blob_store, bucket = _real_storage_settings(tmp_path, "knowledge")
    search_catalog = MeilisearchCatalog(
        create_reader(os.environ["MEILI_CONTRACT_URL"], key_file)
    )
    api = create_app(
        database=database,
        settings=settings,
        blob_store=blob_store,
        search_catalog=search_catalog,
        catalog_state=MongoCatalogState(database),
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
            {
                "catalogId": "catalog-meta",
                "docClass": "catalog-meta",
                "generation": "issue360-real-knowledge",
                "projectionVersion": PROJECTION_VERSION,
            },
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
                    "projectionVersion": PROJECTION_VERSION,
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
                    "status": "healthy",
                    "indexUid": uid,
                    "indexEpoch": epoch,
                }},
                upsert=True,
            )
            _set_catalog_health(database, "issue360-real-knowledge", uid, epoch)
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
                run = database.agent_runs.find_one(
                    {"threadId": thread_id}, sort=[("startedAt", -1)]
                )
                [directory] = _last_search_sources(database, thread_id, run["id"])
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
            section_run = database.agent_runs.find_one(
                {"threadId": thread_id}, sort=[("startedAt", -1)]
            )
            section_sources = _last_search_sources(
                database, thread_id, section_run["id"]
            )
            section_hit = next(item for item in section_sources if item["id"] == section["id"])
            assert section_hit["knowledgeLevel"] == "section"
            assert section_hit["version"] == source["edition"]
            section_output = _last_tool_output(
                database, thread_id, "tool-read_source", section_run["id"]
            )
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
            _set_catalog_health(
                database, "issue360-real-knowledge", uid,
                index_epoch(meili_admin, uid),
            )
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
            collision_run = database.agent_runs.find_one(
                {"threadId": thread_id}, sort=[("startedAt", -1)]
            )
            collision_output = _last_tool_output(
                database, thread_id, "tool-read_source", collision_run["id"]
            )
            assert collision_output["status"] == "unavailable"
            assert "content" not in collision_output

            database.knowledge_sources.update_one(
                {"id": source_id}, {"$set": {"status": "retired"}}
            )
            offline = _post_stream(
                client, auth, "c-draft-1", thread_id,
                _stream_body("目录下线后继续创作", "real-retired-source-message"),
                _run_model("knowledge", "real-retired-source"),
            )
            assert offline.status_code == 200, offline.text
            assert NORMAL_ANSWER in offline.text
            assert source_id not in offline.text
            latest_run = database.agent_runs.find_one(
                {"threadId": thread_id}, sort=[("startedAt", -1)]
            )
            assert latest_run["status"] == "completed"
            latest_message = database.agent_messages.find_one(
                {"runId": latest_run["id"], "role": "assistant"}
            )
            assert latest_message
            assert source_id not in str(latest_message.get("metadata", {}))
            search_parts = [
                part for part in latest_message.get("parts", [])
                if part.get("type") == "tool-search_corpus"
            ]
            assert search_parts
            assert all(
                source_id not in str(part.get("output", {}).get("sources", []))
                for part in search_parts
            )
    finally:
        _cleanup_bucket(blob_store, bucket)
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
    settings, blob_store, bucket = _real_storage_settings(tmp_path, "case-search")
    catalog = MeilisearchCatalog(
        create_reader(os.environ["MEILI_CONTRACT_URL"], key_file)
    )
    api = create_app(
        database=database,
        settings=settings,
        blob_store=blob_store,
        search_catalog=catalog,
        catalog_state=MongoCatalogState(database),
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
        documents.insert(0, {
            "catalogId": "catalog-meta",
            "docClass": "catalog-meta",
            "generation": "issue360-real-case-search",
            "projectionVersion": PROJECTION_VERSION,
        })
        wait_task(meili_admin, index.add_documents(documents))
        database.cases.insert_one({
            "id": version["caseId"],
            "ownerId": "u-360-other-owner",
            "publicationStatus": "public",
            "workflowStatus": "published",
            "publishedVersionId": version["id"],
            "document": version["document"],
        })
        database.case_versions.insert_one({
            **version,
            "kind": "submission",
            "sourceRevision": 1,
            "createdBy": "u-360-other-owner",
            "createdAt": datetime.now(UTC).isoformat(),
        })
        epoch = index_epoch(meili_admin, uid)

        with TestClient(api) as client:
            database.search_catalog_generation.update_one(
                {"_id": "catalog"},
                {"$set": {
                    "generation": "issue360-real-case-search",
                    "indexUid": uid,
                    "indexEpoch": epoch,
                    "projectionVersion": PROJECTION_VERSION,
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
                    "status": "healthy",
                    "indexUid": uid,
                    "indexEpoch": epoch,
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
        _cleanup_bucket(blob_store, bucket)
        if created_index:
            wait_task(meili_admin, meili_admin.delete_index(uid))
        mongo.drop_database(database_name)
        mongo.close()


@pytest.mark.e2e(
    "OBJECT_STORE_ENDPOINT",
    "OBJECT_STORE_ACCESS_KEY_FILE",
    "OBJECT_STORE_SECRET_KEY_FILE",
)
def test_real_three_turn_run_revocation_rechecks_meili_minio_and_http_history(
    tmp_path,
) -> None:
    from tests.test_search_meilisearch_e2e import _meili_client

    mongo = MongoClient(
        os.environ["AUTH_QUERY_MONGODB_URI"], serverSelectionTimeoutMS=5000
    )
    database_name = f"c360turn_{uuid.uuid4().hex}"
    database = mongo[database_name]
    meili_admin, key_file = _meili_client()
    index_uid = f"issue360_three_turn_{uuid.uuid4().hex}"
    blob_id = f"issue360-three-turn-{uuid.uuid4().hex}"
    bucket = f"case-library-360-three-turn-{uuid.uuid4().hex}"
    material_id = f"m-{uuid.uuid4().hex}"
    title = f"合成三轮校内资料-{uuid.uuid4().hex}"
    body_marker = f"合成校内正文标记-{uuid.uuid4().hex}"
    body = f"{body_marker}。仅用于当前资格重验。"
    body_bytes = body.encode("utf-8")
    secret = tmp_path / "app-secret"
    secret.write_text("synthetic-test-secret", encoding="utf-8")
    settings = replace(
        Settings(),
        app_environment="test",
        enable_demo_seed=True,
        session_cookie_secure=False,
        app_secret_file=str(secret),
        object_store_endpoint=os.environ["OBJECT_STORE_ENDPOINT"],
        object_store_bucket=bucket,
        object_store_access_key_file=os.environ["OBJECT_STORE_ACCESS_KEY_FILE"],
        object_store_secret_key_file=os.environ["OBJECT_STORE_SECRET_KEY_FILE"],
    )
    store = minio_blob_store(settings)
    catalog = MeilisearchCatalog(
        create_reader(os.environ["MEILI_CONTRACT_URL"], key_file)
    )
    api = create_app(
        database=database,
        settings=settings,
        blob_store=store,
        search_catalog=catalog,
        catalog_state=MongoCatalogState(database),
    )
    index_created = False
    blob_written = False
    bucket_existed = False

    try:
        bucket_existed = store.client.bucket_exists(bucket)
        store.put(blob_id, BytesIO(body_bytes), len(body_bytes), "text/plain")
        blob_written = True
        material = {
            "id": material_id,
            "status": "active",
            "title": title,
            "summary": f"{title}的合成目录摘要",
            "excerpt": "仅供检索目录展示的合成摘录",
            "accessLevel": "campus",
            "publicReferenceCount": 1,
            "createdBy": "u-issue360-synthetic-owner",
            "blobId": blob_id,
            "filename": "synthetic-campus.txt",
            "mediaType": "text/plain",
            "size": len(body_bytes),
            "publishedAt": "2026-10-08",
        }
        database.materials.insert_one(material)
        wait_task(
            meili_admin,
            meili_admin.create_index(index_uid, {"primaryKey": "catalogId"}),
        )
        index_created = True
        index = meili_admin.index(index_uid)
        wait_task(meili_admin, index.update_settings(catalog_settings()))
        generation = f"issue360-three-turn-{uuid.uuid4().hex}"
        wait_task(
            meili_admin,
            index.add_documents(project_catalog_documents("material", material)),
        )
        wait_task(meili_admin, index.add_documents([{
            "catalogId": "catalog-meta",
            "docClass": "catalog-meta",
            "generation": generation,
            "projectionVersion": PROJECTION_VERSION,
        }]))
        epoch = index_epoch(meili_admin, index_uid)
        database.search_catalog_generation.update_one(
            {"_id": "catalog"},
            {"$set": {
                "generation": generation,
                "indexUid": index_uid,
                "indexEpoch": epoch,
                "projectionVersion": PROJECTION_VERSION,
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
                "worker": "issue360-three-turn",
                "updatedAt": datetime.now(UTC),
                "status": "healthy",
                "indexUid": index_uid,
                "indexEpoch": epoch,
            }},
            upsert=True,
        )

        with TestClient(api) as applicant, TestClient(api) as admin:
            database.search_catalog_generation.update_one(
                {"_id": "catalog"},
                {"$set": {
                    "generation": generation,
                    "indexUid": index_uid,
                    "indexEpoch": epoch,
                    "projectionVersion": PROJECTION_VERSION,
                    "retiredIndexUids": [],
                }},
            )
            username = f"issue360-three-turn-{uuid.uuid4().hex}"
            password = f"Issue360-ThreeTurn-{uuid.uuid4().hex}!a"
            registration = applicant.post(
                "/api/auth/register", json={"username": username, "password": password}
            )
            assert registration.status_code == 201, registration.text
            auth_response = applicant.post(
                "/api/auth/login", json={"username": username, "password": password}
            )
            assert auth_response.status_code == 200, auth_response.text
            auth = auth_response.json()
            user_id = auth["user"]["id"]
            headers = {"X-CSRF-Token": auth["csrfToken"]}
            created_case = applicant.post(
                "/api/cases",
                headers=headers,
                json={
                    "title": "合成无校内资格创作案例",
                    "document": {
                        "type": "doc",
                        "content": [{
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "合成正文段落"}],
                        }],
                    },
                },
            )
            assert created_case.status_code == 200, created_case.text
            case_id = created_case.json()["id"]
            thread_response = applicant.get(f"/api/cases/{case_id}/agent/thread")
            assert thread_response.status_code == 200, thread_response.text
            thread_id = thread_response.json()["id"]

            admin_auth_response = admin.post(
                "/api/auth/login", json={"username": "admin", "password": "admin123"}
            )
            assert admin_auth_response.status_code == 200, admin_auth_response.text
            admin_auth = admin_auth_response.json()

            first = _post_stream(
                applicant, auth, case_id, thread_id,
                _stream_body("先看一个目录标题"),
                _three_turn_title_model(title),
            )
            assert first.status_code == 200, first.text
            assert body_marker not in first.text
            first_run = database.agent_runs.find_one(
                {"threadId": thread_id}, sort=[("startedAt", -1)]
            )
            first_message = database.agent_messages.find_one(
                {"runId": first_run["id"], "role": "assistant"}
            )
            first_dependencies = first_message["metadata"]["_sourceDependencies"]
            assert any(
                ref["id"] == material_id and ref["contentAvailable"] is False
                for ref in first_dependencies
            )
            [metadata_source] = _last_search_sources(
                database, thread_id, first_run["id"]
            )
            assert metadata_source["id"] == material_id
            assert metadata_source["contentAvailable"] is False
            assert body_marker not in str(metadata_source)

            application = applicant.post(
                "/api/auth/campus-access/applications",
                headers=headers,
                json={
                    "applicantName": "合成三轮申请人",
                    "studentNumber": f"SYN-360-{uuid.uuid4().hex[:12]}",
                },
            )
            assert application.status_code == 201, application.text
            decided = admin.post(
                f"/api/admin/campus-access-applications/{application.json()['id']}/decision",
                headers={"X-CSRF-Token": admin_auth["csrfToken"]},
                json={"decision": "approved", "reason": "合成三轮资格人工批准"},
            )
            assert decided.status_code == 200, decided.text
            assert decided.json()["status"] == "approved"
            assert database.users.find_one({"id": user_id})["campus_verified"] is True

            range_target = text_blocks(created_case.json()["document"])[0]

            second = _post_stream(
                applicant, auth, case_id, thread_id,
                _stream_body("读取并引用正文", "three-turn-second-message"),
                _three_turn_range_model(title, material_id, range_target, body_marker),
            )
            assert second.status_code == 200, second.text
            assert body_marker in second.text
            second_run = database.agent_runs.find_one(
                {"threadId": thread_id}, sort=[("startedAt", -1)]
            )
            read_output = _last_tool_output(
                database, thread_id, "tool-read_source", second_run["id"]
            )
            assert read_output["status"] == "ok"
            assert body_marker in read_output["content"]
            second_message = database.agent_messages.find_one(
                {"runId": second_run["id"], "role": "assistant"}
            )
            body_dependencies = second_message["metadata"]["_sourceDependencies"]
            assert any(
                ref["id"] == material_id and ref.get("contentAvailable") is not False
                for ref in body_dependencies
            )
            range_artifact = database.agent_artifacts.find_one(
                {"runId": second_run["id"], "kind": "range"}
            )
            assert range_artifact and range_artifact["status"] == "pending"
            assert any(
                ref["id"] == material_id and ref.get("contentAvailable") is not False
                for ref in range_artifact["sources"]
            )

            blank_case = applicant.post(
                "/api/cases",
                headers=headers,
                json={
                    "title": "合成整篇与直写撤销案例",
                    "document": {"type": "doc", "content": []},
                },
            )
            assert blank_case.status_code == 200, blank_case.text
            blank_case_id = blank_case.json()["id"]
            blank_thread = applicant.get(
                f"/api/cases/{blank_case_id}/agent/thread"
            )
            assert blank_thread.status_code == 200, blank_thread.text
            blank_thread_id = blank_thread.json()["id"]

            document_candidate_response = _post_stream(
                applicant, auth, blank_case_id, blank_thread_id,
                _stream_body("创建整篇候选", "three-turn-document-message"),
                _three_turn_document_model(title, material_id),
            )
            assert document_candidate_response.status_code == 200, (
                document_candidate_response.text
            )
            document_run = database.agent_runs.find_one(
                {"threadId": blank_thread_id}, sort=[("startedAt", -1)]
            )
            assert document_run["status"] == "completed", (
                document_run.get("error"), document_candidate_response.text,
            )
            assert "已创建整篇候选。" in document_candidate_response.text
            document_version = database.case_versions.find_one({
                "caseId": blank_case_id,
                "kind": "ai",
                "sourceRunId": document_run["id"],
            })
            assert document_version
            assert "撤销后不得采纳的整篇候选" in str(document_version["document"])
            document_output = _last_tool_output(
                database, blank_thread_id, "tool-propose_document", document_run["id"]
            )
            assert document_output == {
                "status": "created", "kind": "ai",
                "versionId": document_version["id"],
            }

            entered_model = Event()
            resume_model = Event()
            emitted_tool_calls = Event()
            emitted_after_revoke = f"撤销后不得再次输出-{uuid.uuid4().hex}"
            ai_versions_before = database.case_versions.count_documents({
                "caseId": blank_case_id, "kind": "ai",
            })
            writes_before = database.agent_writes.count_documents(
                {"caseId": blank_case_id}
            )

            def post_third_turn():
                return _post_stream(
                    applicant, auth, blank_case_id, blank_thread_id,
                    _stream_body("只按历史继续", "three-turn-third-message"),
                    _three_turn_history_model(
                        body_marker, emitted_after_revoke, entered_model,
                        resume_model, emitted_tool_calls,
                    ),
                )

            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(post_third_turn)
                try:
                    assert entered_model.wait(20), "第三轮生产 Run 未进入模型历史"
                    revoked = admin.post(
                        f"/api/admin/campus-access-applications/{application.json()['id']}/revoke",
                        headers={"X-CSRF-Token": admin_auth["csrfToken"]},
                        json={"reason": "合成第三轮进行中撤销资格"},
                    )
                    assert revoked.status_code == 200, revoked.text
                    assert revoked.json()["status"] == "revoked"
                    assert database.users.find_one({"id": user_id})[
                        "campus_verified"
                    ] is False
                finally:
                    resume_model.set()
                third = pending.result(timeout=45)

            assert third.status_code == 200, third.text
            assert emitted_tool_calls.is_set()
            assert emitted_after_revoke not in third.text
            third_run = database.agent_runs.find_one(
                {"threadId": blank_thread_id}, sort=[("startedAt", -1)]
            )
            assert third_run["status"] == "cancelled"
            assert database.agent_messages.count_documents({
                "runId": third_run["id"], "role": "assistant",
            }) == 0
            third_tool_names = {
                timing.get("toolName")
                for timing in third_run.get("toolTimings", {}).values()
            }
            assert third_tool_names == set()
            assert not third_run.get("toolTimings")
            assert database.case_versions.count_documents({
                "caseId": blank_case_id, "kind": "ai",
            }) == ai_versions_before
            assert database.agent_writes.count_documents(
                {"caseId": blank_case_id}
            ) == writes_before
            unchanged_blank = database.cases.find_one({"id": blank_case_id})
            assert unchanged_blank["revision"] == 1
            assert unchanged_blank["document"] == {"type": "doc", "content": []}
            assert database.agent_artifacts.count_documents({
                "runId": third_run["id"],
            }) == 0

            for artifact, artifact_case_id, artifact_thread_id in (
                (range_artifact, case_id, thread_id),
            ):
                before_case = database.cases.find_one({"id": artifact_case_id})
                before_writes = database.agent_writes.count_documents(
                    {"caseId": artifact_case_id}
                )
                denied = applicant.post(
                    f"/api/cases/{artifact_case_id}/agent/thread/{artifact_thread_id}"
                    f"/artifacts/{artifact['id']}/decision",
                    headers=headers,
                    json={"decision": "accepted"},
                )
                assert denied.status_code == 409, denied.text
                current_artifact = database.agent_artifacts.find_one(
                    {"id": artifact["id"]}
                )
                assert current_artifact["status"] == "pending"
                after_case = database.cases.find_one({"id": artifact_case_id})
                assert after_case["revision"] == before_case["revision"]
                assert database.agent_writes.count_documents(
                    {"caseId": artifact_case_id}
                ) == before_writes

            snapshot = applicant.get(
                f"/api/cases/{case_id}/agent/threads/{thread_id}"
            )
            assert snapshot.status_code == 200, snapshot.text
            assert body_marker not in snapshot.text
            with applicant.stream(
                "GET", f"/api/cases/{case_id}/agent/thread/{thread_id}/events"
            ) as replay:
                assert replay.status_code == 200, replay.text
                replay_text = "".join(replay.iter_text())
            assert body_marker not in replay_text
            blank_snapshot = applicant.get(
                f"/api/cases/{blank_case_id}/agent/threads/{blank_thread_id}"
            )
            assert blank_snapshot.status_code == 200, blank_snapshot.text
            assert body_marker not in blank_snapshot.text
            with applicant.stream(
                "GET", f"/api/cases/{blank_case_id}/agent/thread/{blank_thread_id}/events"
            ) as replay:
                assert replay.status_code == 200, replay.text
                blank_replay_text = "".join(replay.iter_text())
            assert body_marker not in blank_replay_text

            history = applicant.get(f"/api/cases/{blank_case_id}/history")
            assert history.status_code == 200, history.text
            saved_ai_version = next(
                version for version in history.json()["versions"]
                if version["id"] == document_version["id"]
            )
            assert "撤销后不得采纳的整篇候选" in str(saved_ai_version["document"])
            runs_before_restore = database.agent_runs.count_documents({
                "threadId": blank_thread_id,
            })
            reads_before_restore = database.agent_messages.count_documents({
                "threadId": blank_thread_id,
                "role": "assistant",
                "parts.type": "tool-read_source",
            })
            restored = applicant.post(
                f"/api/cases/{blank_case_id}/lifecycle",
                headers=headers,
                json={
                    "command": "overwrite",
                    "revision": unchanged_blank["revision"],
                    "targetId": document_version["id"],
                },
            )
            assert restored.status_code == 200, restored.text
            assert restored.json()["case"]["document"] == document_version["document"]
            assert database.agent_runs.count_documents({
                "threadId": blank_thread_id,
            }) == runs_before_restore
            assert database.agent_messages.count_documents({
                "threadId": blank_thread_id,
                "role": "assistant",
                "parts.type": "tool-read_source",
            }) == reads_before_restore
            assert database.case_versions.count_documents({
                "caseId": blank_case_id, "kind": "ai",
            }) == ai_versions_before
            assert database.agent_messages.count_documents({
                "runId": third_run["id"], "role": "assistant",
            }) == 0

    finally:
        if blob_written:
            store.remove(blob_id)
        if not bucket_existed and store.client.bucket_exists(bucket):
            store.client.remove_bucket(bucket)
        if index_created:
            wait_task(meili_admin, meili_admin.delete_index(index_uid))
        mongo.drop_database(database_name)
        mongo.close()
