"""领域工具契约：检索规模与游标、标签目录、读源状态、版本身份与只读装配。"""

from __future__ import annotations

import asyncio
import io
from fastapi.testclient import TestClient

from app.modules.agent.case_area import dedupe_refs, retained_sources
from app.modules.agent.deps import ToolDeps
from app.modules.agent.models import ArtifactTarget
from app.modules.agent.repository import AgentRepository
from app.modules.agent.search import list_tag_catalog, search_platform
from app.modules.agent.skills import domain_tools, propose_revision, read_source
from app.modules.agent.source_reader import read_source as read_domain_source
from app.modules.search.meilisearch import CatalogMetadata, CatalogPage, CatalogRequest

SECRET = "test-app-secret"


class RecordingCatalog:
    def __init__(self, pages: list[CatalogPage]):
        self.pages = pages
        self.requests: list[CatalogRequest] = []

    def health(self, *_args) -> None:
        return None

    def search(self, request) -> CatalogPage:
        self.requests.append(request)
        return self.pages[min(len(self.requests) - 1, len(self.pages) - 1)]


class Ctx:
    def __init__(self, deps: ToolDeps):
        self.deps = deps


def _deps(database, catalog, user=None, secret_file=None) -> ToolDeps:
    from tests.conftest import ReadyCatalogState

    return ToolDeps(
        database=database, case_id="c-draft-1", thread_id="thread-1", run_id="run-1",
        user=user or {"id": "u-1", "role": "user"}, catalog=catalog,
        catalog_state=ReadyCatalogState(database), secret_path=str(secret_file),
    )


def _secret_file(tmp_path):
    path = tmp_path / "app-secret"
    path.write_text(SECRET, encoding="utf-8")
    return path


def _page(items: list[dict], total: int, has_next: bool) -> CatalogPage:
    metadata = CatalogMetadata(
        total, {"all": total, "case": total, "knowledge": 0, "material": 0}, {},
    )
    return CatalogPage(items, metadata, has_next, False)


ITEM_A = {"id": "c-02", "kind": "case", "title": "案例A", "summary": "科学家精神案例"}
ITEM_B = {"id": "mc-1", "kind": "material", "title": "素材B", "summary": "讲义素材"}


def _test_db():
    from tests.conftest import _test_database

    return _test_database()


def _seed_source_case(database) -> None:
    _seed_catalog_case(database)
    _seed_versioned_sources(database)
    _seed_working_case(database)


def _seed_catalog_case(database) -> None:
    database.cases.insert_one({
        "id": "c-02", "ownerId": "u-other", "publicationStatus": "public",
        "workflowStatus": "published", "publishedVersionId": "cv-seed-c-02-v1",
        "revision": 1, "title": "案例A", "document": {"type": "doc", "content": []},
    })
    database.case_versions.insert_one({
        "id": "cv-seed-c-02-v1", "caseId": "c-02", "number": 1,
        "title": "案例A 发布版",
        "document": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "案例A发布正文"}]},
        ]},
    })


def _seed_versioned_sources(database) -> None:
    database.cases.insert_one({
        "id": "c-src", "ownerId": "u-other", "publicationStatus": "public",
        "workflowStatus": "published", "publishedVersionId": "cv-2", "revision": 1,
        "title": "来源案例", "document": {"type": "doc", "content": []},
    })
    for number, content in [(1, "第一版内容"), (2, "第二版内容")]:
        database.case_versions.insert_one({
            "id": f"cv-{number}", "caseId": "c-src", "number": number,
            "title": f"来源案例 v{number}", "document": {"type": "doc", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": content}]},
            ]},
        })
    database.lifecycle_events.insert_one(
        {"caseId": "c-src", "action": "approve", "versionId": "cv-1"}
    )


def _seed_working_case(database) -> None:
    database.cases.insert_one({
        "id": "c-draft-1", "ownerId": "u-1", "revision": 1,
        "workflowStatus": "draft", "title": "草稿案例",
        "document": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "原段落"}]},
        ]},
    })
    database.case_sources.insert_many([
        {"id": "src-a", "sourceType": "case", "caseId": "c-draft-1",
         "sourceCaseId": "c-src", "versionId": "cv-1", "versionNumber": 1,
         "title": "来源案例 v1", "contentAvailable": True, "createdAt": "t1"},
        {"id": "src-b", "sourceType": "case", "caseId": "c-draft-1",
         "sourceCaseId": "c-src", "versionId": "cv-2", "versionNumber": 2,
         "title": "来源案例 v2", "contentAvailable": True, "createdAt": "t2"},
    ])


def test_search_tool_reports_scale_condition_and_keeps_hits_stable(tmp_path) -> None:
    catalog = RecordingCatalog([_page([ITEM_A], 42, True), _page([ITEM_B], 42, False)])
    deps = _deps(_test_db(), catalog, secret_file=_secret_file(tmp_path))
    first = search_platform(deps, "科学家精神", kind="case", page_size=99)
    assert first["status"] == "ok" and first["total"] == 42
    assert first["pageSize"] == 20 and first["nextCursor"]
    assert first["sources"][0]["id"] == "c-02"
    second = search_platform(deps, "科学家精神", kind="case", page_size=20,
                             cursor=first["nextCursor"])
    assert second["sources"][0]["id"] == "mc-1"
    request = catalog.requests[1]
    assert request.offset == 20 and not request.include_metadata
    assert [ref.identity() for ref in deps.hits] == [
        ("case", "c-02", ""), ("material", "mc-1", ""),
    ]
    assert deps.sources == []


def test_search_tool_sends_nested_tag_condition(tmp_path) -> None:
    database = _test_db()
    for tag_id in ("tag-a", "tag-b", "tag-c"):
        database.tags.insert_one({"id": tag_id, "groupId": "tgg", "name": tag_id, "sortKey": 1})
    catalog = RecordingCatalog([_page([], 0, False)])
    deps = _deps(database, catalog, secret_file=_secret_file(tmp_path))
    condition = {"op": "and", "children": [
        {"tagId": "tag-a"},
        {"op": "or", "children": [{"tagId": "tag-b"}, {"tagId": "tag-c"}]},
    ]}
    result = search_platform(deps, "条件检索", tag_condition=condition)
    assert result["status"] == "ok"
    assert result["tagCondition"] == condition
    assert catalog.requests[0].tag_condition is not None
    assert result["sources"] == []


def test_unknown_tag_condition_returns_error_status(tmp_path) -> None:
    deps = _deps(_test_db(), RecordingCatalog([_page([], 0, False)]), secret_file=_secret_file(tmp_path))
    result = search_platform(deps, "坏条件", tag_condition={"op": "and", "children": [
        {"tagId": "tag-missing"},
    ]})
    assert result["status"] == "error" and "标签不存在" in result["detail"]


def test_tag_catalog_tool_lists_real_groups_and_tags() -> None:
    database = _test_db()
    database.tag_groups.insert_one(
        {"id": "tgg-1", "name": "思政元素", "requiredForSubmission": False, "sortKey": 1}
    )
    database.tags.insert_one(
        {"id": "tag-1", "groupId": "tgg-1", "name": "科学家精神", "sortKey": 1}
    )
    result = asyncio.run(list_tag_catalog(Ctx(_deps(database, None))))
    group = result["groups"][0]
    assert group["id"] == "tgg-1"
    assert group["tags"][0]["id"] == "tag-1"


def test_case_area_keeps_v1_v2_distinct_across_republication() -> None:
    database = _test_db()
    _seed_source_case(database)
    refs = retained_sources(database, "c-draft-1")
    assert [(ref.id, ref.version, ref.version_id) for ref in refs] == [
        ("src-a", "v1", "cv-1"), ("src-b", "v2", "cv-2"),
    ]
    assert dedupe_refs(refs) == refs
    user = {"id": "u-1", "role": "user"}
    first = read_domain_source(database, None, user, "c-draft-1", "case", "src-a")
    second = read_domain_source(database, None, user, "c-draft-1", "case", "src-b")
    assert first["source"]["versionId"] == "cv-1"
    assert "第一版内容" in first["content"]
    assert second["source"]["versionId"] == "cv-2"
    database.cases.update_one({"id": "c-src"}, {"$set": {"publishedVersionId": "cv-3"}})
    again = read_domain_source(database, None, user, "c-draft-1", "case", "src-a")
    assert again["source"]["versionId"] == "cv-1"


def test_read_statuses_are_explicit(tmp_path) -> None:
    from tests.conftest import MemoryBlobStore

    database = _test_db()
    store = MemoryBlobStore()
    _seed_source_case(database)
    user = {"id": "u-1", "role": "user"}
    database.cases.update_one(
        {"id": "c-src"}, {"$set": {"publicationStatus": "private"}}
    )
    denied = read_domain_source(database, store, user, "c-draft-1", "case", "src-a")
    assert denied["status"] == "no_access"
    database.cases.delete_one({"id": "c-src"})
    missing = read_domain_source(database, store, user, "c-draft-1", "case", "src-a")
    assert missing["status"] == "unavailable"
    unknown = read_domain_source(database, store, user, "c-draft-1", "case", "c-none")
    assert unknown["status"] == "error"
    _assert_empty_image_source(database, store, user)


def _assert_empty_image_source(database, store, user) -> None:
    store.put("blob-1", io.BytesIO(b"\x89PNG"), 4, "image/png")
    database.attachments.insert_one({
        "id": "att-1", "caseId": "c-draft-1", "name": "图.png",
        "mediaType": "image/png", "size": 3, "accessLevel": "public",
        "blobId": "blob-1", "searchText": "", "createdAt": "t1",
    })
    empty = read_domain_source(database, store, user, "c-draft-1", "attachment", "att-1")
    assert empty["status"] == "empty"


def test_frozen_version_area_for_read_only_integration() -> None:
    database = _test_db()
    _seed_source_case(database)
    database.case_versions.insert_one({
        "id": "cv-d1", "caseId": "c-draft-1", "number": 1, "title": "草稿版本一",
        "document": {"type": "doc", "content": []},
        "caseSources": [
            {"id": "src-a", "sourceType": "case", "caseId": "c-draft-1",
             "sourceCaseId": "c-src", "versionId": "cv-1", "versionNumber": 1,
             "title": "来源案例 v1", "contentAvailable": True, "createdAt": "t1"},
        ],
    })
    refs = retained_sources(database, "c-draft-1", version_id="cv-d1")
    assert [(ref.id, ref.version_id) for ref in refs] == [("src-a", "cv-1")]
    result = read_domain_source(
        database, None, {"id": "u-1", "role": "user"}, "c-draft-1", "case", "src-a", "cv-d1",
    )
    assert result["source"]["versionId"] == "cv-1"


def test_write_tool_excluded_and_reported_for_read_only_runs() -> None:
    write_names = {tool.__name__ for tool in domain_tools(True)}
    read_names = {tool.__name__ for tool in domain_tools(False)}
    assert "propose_revision" in write_names
    assert not {"propose_revision"} & read_names
    assert {"search_corpus", "list_tag_catalog", "read_source"} <= read_names
    repository = AgentRepository(_test_db())
    thread = repository.default_thread("c-draft-1", "u-1", "published-v1")
    run = repository.start_run(
        thread, "u-1", [{"type": "text", "text": "只读"}], {}, "assistant-x",
    )
    assert run.read_only is True


def test_proposal_only_attaches_evidence_actually_read(tmp_path) -> None:
    database = _test_db()
    _seed_source_case(database)
    thread = AgentRepository(database).default_thread("c-draft-1", "u-1")
    run = AgentRepository(database).start_run(
        thread, "u-1", [{"type": "text", "text": "修订"}], {}, "assistant-x",
        base_revision=1, target=ArtifactTarget(paragraph_index=0, quote="原段落"))
    catalog = RecordingCatalog([_page([ITEM_A, ITEM_B], 2, False)])
    deps = _deps(database, catalog, secret_file=_secret_file(tmp_path))
    deps.thread_id, deps.run_id = thread.id, run.id
    ctx = Ctx(deps)
    from app.modules.agent.search import search_corpus

    asyncio.run(search_corpus(ctx, "科学家精神"))
    asyncio.run(read_source(ctx, "case", "c-02"))
    artifact = asyncio.run(propose_revision(ctx, 0, "替换后的段落", "依据来源"))
    assert [item["id"] for item in artifact["sources"]] == ["c-02"]
    assert artifact["sources"][0]["versionId"] == "cv-seed-c-02-v1"


# ---- 消息通道（HTTP 层）：data-source / data-selection 服务端校验 ----

def _login(client):
    response = client.post("/api/auth/login", json={"username": "user", "password": "user123"})
    assert response.status_code == 200
    return response.json()


def _post_parts(client, auth, case_id, parts):
    from app.modules.agent.runtime import agent
    from pydantic_ai.models.test import TestModel

    thread_id = client.get(f"/api/cases/{case_id}/agent/thread").json()["id"]
    with agent.override(model=TestModel(call_tools=[], custom_output_text="好的")):
        return client.post(
            f"/api/cases/{case_id}/agent/thread/{thread_id}/stream",
            headers={"X-CSRF-Token": auth["csrfToken"]},
            json={
                "id": "browser", "trigger": "submit-message",
                "messages": [{"id": "client-message", "role": "user", "parts": parts}],
            },
        )


def _seed_area_case(database) -> None:
    database.cases.insert_one({
        "id": "c-src", "ownerId": "u-other", "publicationStatus": "public",
        "workflowStatus": "published", "publishedVersionId": "cv-1", "revision": 1,
        "title": "来源案例", "document": {"type": "doc", "content": []},
    })
    database.case_versions.insert_one({
        "id": "cv-1", "caseId": "c-src", "number": 1, "title": "来源案例 v1",
        "document": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "来源正文"}]},
        ]},
    })
    database.case_sources.insert_one({
        "id": "src-a", "sourceType": "case", "caseId": "c-draft-1",
        "sourceCaseId": "c-src", "versionId": "cv-1", "versionNumber": 1,
        "title": "来源案例 v1", "contentAvailable": True, "createdAt": "t1",
    })


def test_forged_data_source_rejected_before_run(client: TestClient) -> None:
    _seed_area_case(client.app.state.database)
    auth = _login(client)
    response = _post_parts(client, auth, "c-draft-1", [
        {"type": "text", "text": "请用这个来源"},
        {"type": "data-source", "data": {"sourceType": "case", "id": "src-forged"}},
    ])
    assert response.status_code == 422
    database = client.app.state.database
    assert database.agent_runs.count_documents({}) == 0
    assert database.agent_messages.count_documents({}) == 0


def test_stable_data_source_selection_starts_run(client: TestClient) -> None:
    _seed_area_case(client.app.state.database)
    auth = _login(client)
    response = _post_parts(client, auth, "c-draft-1", [
        {"type": "text", "text": "请用这个来源"},
        {"type": "data-source", "data": {"sourceType": "case", "id": "src-a"}},
    ])
    assert response.status_code == 200, response.text
    run = client.app.state.database.agent_runs.find_one({}, {"_id": 0})
    assert run["status"] == "completed"


def test_forged_document_selection_rejected_before_run(client: TestClient) -> None:
    auth = _login(client)
    response = _post_parts(client, auth, "c-draft-1", [
        {"type": "text", "text": "请改这段"},
        {"type": "data-selection", "data": {"quote": "浏览器伪造的段落"}},
    ])
    assert response.status_code == 422
    assert client.app.state.database.agent_runs.count_documents({}) == 0


def test_document_selection_quote_resolved_server_side(client: TestClient) -> None:
    auth = _login(client)
    response = _post_parts(client, auth, "c-draft-1", [
        {"type": "text", "text": "请改这段"},
        {"type": "data-selection", "data": {"quote": "三类立场背后是短期交付、质量标准与长期能力安全之间的价值排序问题。"}},
    ])
    assert response.status_code == 200, response.text
    run = client.app.state.database.agent_runs.find_one({}, {"_id": 0})
    assert run["status"] == "completed"
