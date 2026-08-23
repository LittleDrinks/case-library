from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

import mongomock
import pytest
from pymongo.errors import PyMongoError

import app.modules.search.worker as search_worker
from app.modules.search.indexer import CatalogRebuilder
from app.modules.search.meilisearch import (
    CatalogMetadata,
    CatalogPage,
    SearchUnavailable,
)
from app.modules.search.outbox import SearchOutbox
from app.modules.search.service import search_catalog
from app.modules.search.worker import CatalogConsumer, WorkerHeartbeat
from conftest import ReadyCatalogState


class MissingIndex(Exception):
    code = "index_not_found"


class PassthroughSession:
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def with_transaction(self, callback):
        return callback(None)


class BeforeTransactionSession(PassthroughSession):
    def __init__(self, before) -> None:
        self.before = before

    def with_transaction(self, callback):
        self.before()
        return callback(None)


class FakeIndex:
    def __init__(self, client, uid: str) -> None:
        self.client = client
        self.uid = uid

    def update_settings(self, settings: dict) -> dict:
        self.client.settings[self.uid] = settings
        return self.client.task(self.uid)

    def add_documents(self, documents: list[dict], primary_key: str) -> dict:
        if self.client.fail_uid == self.uid:
            raise RuntimeError("indexing failed")
        if self.client.before_add:
            callback, self.client.before_add = self.client.before_add, None
            callback(self.uid)
        rows = self.client.documents.setdefault(self.uid, {})
        rows.update({row[primary_key]: row for row in documents})
        task = self.client.task(self.uid)
        if self.client.after_add:
            callback, self.client.after_add = self.client.after_add, None
            callback()
        if self.client.on_add:
            self.client.on_add()
        return task

    def delete_documents(self, ids: list[str]) -> dict:
        for document_id in ids:
            self.client.documents[self.uid].pop(document_id, None)
        return self.client.task(self.uid)


class FakeMeiliClient:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, dict]] = {}
        self.settings: dict[str, dict] = {}
        self.fail_uid: str | None = None
        self.fail_delete_uid: str | None = None
        self.before_add = None
        self.after_add = None
        self.on_add = None
        self.before_wait = None
        self.tasks = 0
        self.epochs: dict[str, str] = {}

    def task(self, uid: str | None = None) -> dict:
        self.tasks += 1
        if uid:
            self.epochs[uid] = f"epoch-{self.tasks}"
        return {"taskUid": self.tasks}

    def get_index(self, uid: str) -> FakeIndex:
        if uid not in self.documents:
            raise MissingIndex(uid)
        return FakeIndex(self, uid)

    def create_index(self, uid: str, options: dict) -> dict:
        assert options == {"primaryKey": "catalogId"}
        self.documents[uid] = {}
        return self.task(uid)

    def index(self, uid: str) -> FakeIndex:
        return FakeIndex(self, uid)

    def get_raw_index(self, uid: str) -> dict:
        return {"updatedAt": self.epochs[uid]}

    def wait_for_task(self, _uid: int, **_options) -> dict:
        if self.before_wait:
            callback, self.before_wait = self.before_wait, None
            callback()
        return {"status": "succeeded"}

    def delete_index(self, uid: str) -> dict:
        if self.fail_delete_uid == uid:
            raise RuntimeError("cleanup failed")
        self.documents.pop(uid, None)
        self.settings.pop(uid, None)
        return self.task()


class VisibleMaterialCatalog:
    def __init__(self, db, client) -> None:
        self.db, self.client = db, client

    def search(self, request) -> CatalogPage:
        if (
            self.client.get_raw_index(request.index_uid)["updatedAt"]
            != request.index_epoch
        ):
            raise SearchUnavailable("检索目录正在同步")
        excluded = {(key.kind, key.id) for key in request.excluded_keys}
        documents = _current_documents(self.db, self.client).values()
        items = [
            row
            for row in documents
            if row.get("docClass") == "material-full"
            and (row["kind"], row["id"]) not in excluded
        ]
        counts = {"all": len(items), "case": 0, "knowledge": 0, "material": len(items)}
        return CatalogPage(items, CatalogMetadata(len(items), counts, {}), False, False)


def _seed_cases(db) -> None:
    db.cases.insert_many(
        [
            {
                "id": "c-public",
                "publicationStatus": "public",
                "publishedVersionId": "v-public",
                "publishedAt": "2026-08-13",
                "ownerId": "u-owner",
            },
            {"id": "c-draft", "publicationStatus": "none"},
        ]
    )
    db.case_versions.insert_many(
        [
            {
                "id": "v-public",
                "caseId": "c-public",
                "title": "公开案例",
                "summary": "摘要",
                "document": {"type": "doc", "content": []},
                "attachments": [],
                "metadata": {},
                "materials": [{"id": "m-1"}],
            },
            {"id": "v-draft", "caseId": "c-draft", "title": "草稿", "metadata": {}},
        ]
    )


def _seed_knowledge(db) -> None:
    db.knowledge_sources.insert_many(
        [
            {"id": "ks-1", "title": "教材", "status": "active"},
            {"id": "ks-off", "title": "停用教材", "status": "disabled"},
        ]
    )
    db.knowledge_sections.insert_many(
        [
            {
                "id": "kn-1",
                "sourceId": "ks-1",
                "chapterId": "kc-1",
                "chapter": "第一章",
                "index": 1,
                "title": "科学精神",
            },
            {
                "id": "kn-off",
                "sourceId": "ks-off",
                "chapterId": "kc-off",
                "chapter": "停用章",
                "index": 1,
                "title": "停用节",
            },
        ]
    )


def _seed_materials(db) -> None:
    db.materials.insert_many(
        [
            {
                "id": "m-1",
                "title": "素材",
                "status": "active",
                "accessLevel": "public",
                "createdBy": "u-1",
                "publicReferenceCount": 1,
            },
            {
                "id": "m-off",
                "title": "停用素材",
                "status": "disabled",
                "accessLevel": "public",
                "createdBy": "u-1",
                "publicReferenceCount": 0,
            },
        ]
    )
    db.case_materials.insert_one({"caseId": "c-draft", "materialId": "m-1"})


def database():
    db = mongomock.MongoClient()["catalog_index_test"]
    db.client.start_session = lambda: PassthroughSession()
    _seed_cases(db)
    _seed_knowledge(db)
    _seed_materials(db)
    return db


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 14, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


class FailedGenerationDatabase:
    def __init__(self, database) -> None:
        self._database = database

    def __getattr__(self, name: str):
        if name == "search_catalog_generation":
            return self
        return getattr(self._database, name)

    def replace_one(self, *_args, **_kwargs) -> None:
        raise RuntimeError("generation write failed")

    def find_one(self, *args, **kwargs):
        return self._database.search_catalog_generation.find_one(*args, **kwargs)


def _set_catalog(
    db, client, uid="catalog-old", generation="initial", documents=None
) -> None:
    client.epochs[uid] = "epoch-0"
    marker = {
        "_id": "catalog",
        "generation": generation,
        "indexUid": uid,
        "indexEpoch": client.epochs[uid],
        "retiredIndexUids": [],
    }
    db.search_catalog_generation.replace_one({"_id": "catalog"}, marker, upsert=True)
    client.documents[uid] = documents or {}


def _current_documents(db, client) -> dict[str, dict]:
    marker = db.search_catalog_generation.find_one({"_id": "catalog"})
    return client.documents[marker["indexUid"]]


def _assert_rebuilt(db, client: FakeMeiliClient) -> None:
    expected_ids = {
        "catalog-meta",
        "case-c-public-public",
        "case-c-public-campus",
        "case-c-public-private",
        "knowledge-source-ks-1",
        "knowledge-section-kn-1",
        "material-m-1-full",
        "material-m-1-restricted",
    }
    documents = _current_documents(db, client)
    assert set(documents) == expected_ids
    material = documents["material-m-1-full"]
    assert material["workingCaseIds"] == ["c-draft"]
    assert material["publishedVersionIds"] == ["v-public"]
    restricted = documents["material-m-1-restricted"]
    assert restricted["searchableText"] == "素材"
    assert "summary" not in restricted


def _rebuilder(db, client, uid: str, clock=None) -> CatalogRebuilder:
    return CatalogRebuilder(
        db,
        client,
        "catalog",
        build_uid=lambda: uid,
        clock=clock,
    )


def _wait_until(predicate) -> None:
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.001)
    raise AssertionError("condition was not reached")


def _lease_covers(db, clock: Clock, seconds: int) -> bool:
    state = db.search_catalog_state.find_one({"_id": "catalog"})
    expires = state["leaseExpiresAt"].replace(tzinfo=UTC)
    return expires > clock.now + timedelta(seconds=seconds)


def _fail_heartbeat_during_wait(monkeypatch, client) -> None:
    allow_failure, failed = threading.Event(), threading.Event()
    renew = SearchOutbox.renew_pause

    def fail_in_background(self, owner: str) -> bool:
        background = threading.current_thread() is not threading.main_thread()
        if background and allow_failure.is_set():
            failed.set()
            raise RuntimeError("heartbeat unavailable")
        return renew(self, owner)

    def fail_during_wait() -> None:
        allow_failure.set()
        assert failed.wait(1)

    monkeypatch.setattr(SearchOutbox, "renew_pause", fail_in_background)
    client.before_wait = fail_during_wait


def _contend_during_load(db, client, observed: dict) -> None:
    contender = _rebuilder(db, client, "catalog-build-b")
    before = db.search_catalog_state.find_one({"_id": "catalog"})
    tasks = client.tasks
    with pytest.raises(RuntimeError, match="检索目录正在重建"):
        contender.rebuild()
    after = db.search_catalog_state.find_one({"_id": "catalog"})
    observed["owner"] = (before["leaseOwner"], after["leaseOwner"])
    observed["tasks"] = (tasks, client.tasks)


def _expire_claim(db) -> None:
    expired = datetime(2000, 1, 1, tzinfo=UTC)
    db.search_outbox.update_one(
        {"_id": "material:m-1"},
        {"$set": {"leaseExpiresAt": expired}},
    )


def _set_material(db, title: str, status: str) -> None:
    db.materials.update_one(
        {"id": "m-1"},
        {"$set": {"title": title, "status": status}},
    )


def _record_material(queue: SearchOutbox, revoke: bool = False) -> int:
    revoked = ["material:m-1"] if revoke else []
    return queue.record(["material:m-1"], revoke=revoked, session=None)


def _search_materials(db, client, secret_path) -> dict:
    WorkerHeartbeat(db, "search-worker").pulse()
    return search_catalog(
        db,
        VisibleMaterialCatalog(db, client),
        ReadyCatalogState(db),
        None,
        "",
        "material",
        None,
        20,
        {},
        str(secret_path),
    )


def _pending_material(db, client) -> SearchOutbox:
    _set_catalog(db, client)
    queue = SearchOutbox(db)
    _record_material(queue)
    return queue


def _cursor_secret(tmp_path):
    secret = tmp_path / "cursor-secret"
    secret.write_bytes(b"test-cursor-secret")
    return secret


def _revoke_during_old_write(db, client, queue) -> None:
    _expire_claim(db)
    _set_material(db, "已撤权素材", "disabled")
    _record_material(queue, revoke=True)
    assert CatalogConsumer(db, client).process_one("worker-new") is True


def _schedule_interleave(db, client, final_status: str) -> SearchOutbox:
    queue = SearchOutbox(db)
    _record_material(queue)
    second = CatalogConsumer(db, client)

    def publish_final() -> None:
        _set_material(db, "最终素材", final_status)
        _record_material(queue, revoke=final_status != "active")

    def handoff() -> None:
        _expire_claim(db)
        _set_material(db, "中间素材", "active")
        _record_material(queue)
        assert second.process_one("worker-2") is True
        client.after_add = publish_final

    client.after_add = handoff
    return queue


def _lose_lease_before_complete(db, queue: SearchOutbox) -> None:
    _expire_claim(db)
    _set_material(db, "事务竞态素材", "active")
    _record_material(queue)


def _interleaved_session(db, queue):
    def before() -> None:
        _lose_lease_before_complete(db, queue)

    return BeforeTransactionSession(before)


def test_rebuild_atomically_replaces_catalog_from_business_truth() -> None:
    client, db = FakeMeiliClient(), database()
    _set_catalog(db, client, documents={"old": {"catalogId": "old"}})
    rebuilder = CatalogRebuilder(
        db, client, "catalog", build_uid=lambda: "catalog-build"
    )

    count = rebuilder.rebuild()

    assert count == 7
    _assert_rebuilt(db, client)
    settings = client.settings["catalog-build"]
    assert "accessLevel" in settings["filterableAttributes"]
    assert "id" in settings["filterableAttributes"]
    assert settings["searchableAttributes"] == ["title", "searchableText"]
    assert settings["pagination"] == {"maxTotalHits": 25_000}
    assert "searchableText" not in settings["displayedAttributes"]
    assert "catalog-old" not in client.documents
    assert client.documents["catalog-build"]
    assert db.search_catalog_state.count_documents({}) == 0


def test_rebuild_publishes_one_generation_to_mongo_and_catalog() -> None:
    client, db = FakeMeiliClient(), database()
    rebuilder = CatalogRebuilder(
        db, client, "catalog", build_uid=lambda: "catalog-build"
    )

    rebuilder.rebuild()

    marker = db.search_catalog_generation.find_one({"_id": "catalog"})
    document = client.documents[marker["indexUid"]]["catalog-meta"]
    assert set(marker) == {
        "_id",
        "generation",
        "indexUid",
        "indexEpoch",
        "retiredIndexUids",
    }
    assert marker["generation"] == document["generation"]
    assert marker["indexUid"] == "catalog-build"
    assert marker["generation"]
    assert marker["indexEpoch"] == client.get_raw_index("catalog-build")["updatedAt"]


def test_rebuild_refuses_to_replace_an_existing_owner() -> None:
    client, db = FakeMeiliClient(), database()
    assert SearchOutbox(db).pause("rebuild-a") is True

    with pytest.raises(RuntimeError, match="检索目录正在重建"):
        _rebuilder(db, client, "catalog-build-b").rebuild()

    state = db.search_catalog_state.find_one({"_id": "catalog"})
    assert state["leaseOwner"] == "rebuild-a"
    assert client.tasks == 0


def test_rebuild_takes_over_an_expired_crash_lease() -> None:
    client, db, clock = FakeMeiliClient(), database(), Clock()
    SearchOutbox(db, clock).pause("crashed-rebuild")
    clock.advance(30)

    count = _rebuilder(db, client, "catalog-build", clock).rebuild()

    assert count == 7
    _assert_rebuilt(db, client)
    assert db.search_catalog_state.count_documents({}) == 0


def test_rebuild_renews_its_lease_for_each_build_batch(monkeypatch) -> None:
    client, db, clock = FakeMeiliClient(), database(), Clock()
    monkeypatch.setattr("app.modules.search.indexer.BATCH_SIZE", 1)
    queue = SearchOutbox(db, clock)
    _record_material(queue)
    blocked = []

    def cross_lease_window() -> None:
        clock.advance(20)
        blocked.append(CatalogConsumer(db, client, clock).process_one("worker"))

    client.on_add = cross_lease_window

    count = _rebuilder(db, client, "catalog-build", clock).rebuild()

    assert count == 7
    assert blocked and not any(blocked)
    _assert_rebuilt(db, client)


def test_rebuild_heartbeat_keeps_lease_during_one_slow_meili_operation(
    monkeypatch,
) -> None:
    client, db, clock = FakeMeiliClient(), database(), Clock()
    monkeypatch.setattr("app.modules.search.outbox.REBUILD_HEARTBEAT_SECONDS", 0.005)

    def cross_two_lease_windows() -> None:
        clock.advance(20)
        _wait_until(lambda: _lease_covers(db, clock, 20))
        clock.advance(20)
        _wait_until(lambda: _lease_covers(db, clock, 20))

    client.before_wait = cross_two_lease_windows

    assert _rebuilder(db, client, "catalog-build", clock).rebuild() == 7
    _assert_rebuilt(db, client)


def test_rebuild_heartbeat_failure_prevents_publish_and_removes_build(
    monkeypatch,
) -> None:
    client, db, clock = FakeMeiliClient(), database(), Clock()
    _set_catalog(db, client)
    monkeypatch.setattr("app.modules.search.outbox.REBUILD_HEARTBEAT_SECONDS", 0.005)
    _fail_heartbeat_during_wait(monkeypatch, client)

    with pytest.raises(RuntimeError, match="重建租约已失效"):
        _rebuilder(db, client, "catalog-build", clock).rebuild()

    marker = db.search_catalog_generation.find_one({"_id": "catalog"})
    assert marker["indexUid"] == "catalog-old"
    assert "catalog-build" not in client.documents
    assert db.search_catalog_state.count_documents({}) == 0


def test_rebuild_does_not_publish_after_another_owner_takes_over() -> None:
    client, db, clock = FakeMeiliClient(), database(), Clock()
    _set_catalog(db, client)

    def take_over() -> None:
        clock.advance(30)
        SearchOutbox(db, clock).pause("new-rebuild")

    client.on_add = take_over

    with pytest.raises(RuntimeError, match="重建租约已失效"):
        _rebuilder(db, client, "catalog-build", clock).rebuild()

    marker = db.search_catalog_generation.find_one({"_id": "catalog"})
    state = db.search_catalog_state.find_one({"_id": "catalog"})
    assert marker["indexUid"] == "catalog-old"
    assert state["leaseOwner"] == "new-rebuild"
    assert "catalog-build" not in client.documents


def test_interleaved_rebuild_keeps_the_first_owner_until_completion() -> None:
    client, db, observed = FakeMeiliClient(), database(), {}
    client.after_add = lambda: _contend_during_load(db, client, observed)

    _rebuilder(db, client, "catalog-build-a").rebuild()

    assert observed["owner"][0] == observed["owner"][1]
    assert observed["tasks"][0] == observed["tasks"][1]
    assert "catalog-build-b" not in client.documents
    assert db.search_catalog_state.count_documents({}) == 0


def test_rebuild_failure_keeps_stable_catalog_untouched() -> None:
    client, db = FakeMeiliClient(), database()
    stable = {"old": {"catalogId": "old", "title": "仍可检索"}}
    _set_catalog(db, client, documents=stable.copy())
    client.fail_uid = "catalog-build"
    rebuilder = CatalogRebuilder(
        db, client, "catalog", build_uid=lambda: "catalog-build"
    )

    with pytest.raises(RuntimeError, match="indexing failed"):
        rebuilder.rebuild()

    assert _current_documents(db, client) == stable
    assert "catalog-build" not in client.documents
    assert db.search_catalog_state.count_documents({}) == 0


def test_generation_write_failure_keeps_published_catalog() -> None:
    client, db = FakeMeiliClient(), database()
    old = {
        "catalog-meta": {
            "catalogId": "catalog-meta",
            "generation": "old-generation",
        }
    }
    _set_catalog(db, client, generation="old-generation", documents=old)
    wrapped = FailedGenerationDatabase(db)
    rebuilder = CatalogRebuilder(wrapped, client, "catalog", lambda: "catalog-build")

    with pytest.raises(RuntimeError, match="generation write failed"):
        rebuilder.rebuild()

    marker = db.search_catalog_generation.find_one({"_id": "catalog"})
    assert marker == {
        "_id": "catalog",
        "generation": "old-generation",
        "indexUid": "catalog-old",
        "indexEpoch": "epoch-0",
        "retiredIndexUids": [],
    }
    assert "catalog-build" not in client.documents
    assert db.search_catalog_state.count_documents({}) == 0


def test_retired_cleanup_failure_does_not_negate_publication_and_is_retried() -> None:
    client, db = FakeMeiliClient(), database()
    _set_catalog(db, client, documents={"old": {"catalogId": "old"}})
    client.fail_delete_uid = "catalog-old"
    rebuilder = CatalogRebuilder(
        db, client, "catalog", build_uid=lambda: "catalog-build"
    )

    assert rebuilder.rebuild() == 7

    _assert_rebuilt(db, client)
    marker = db.search_catalog_generation.find_one({"_id": "catalog"})
    assert marker["retiredIndexUids"] == ["catalog-old"]
    assert "catalog-old" in client.documents
    assert db.search_catalog_state.count_documents({}) == 0

    client.fail_delete_uid = None
    _rebuilder(db, client, "catalog-next").rebuild()

    assert "catalog-old" not in client.documents
    assert "catalog-build" not in client.documents


def test_consumer_reloads_truth_then_upserts_and_removes_caught_up_row() -> None:
    client, db = FakeMeiliClient(), database()
    _set_catalog(db, client)
    db.search_outbox.insert_one(
        {
            "_id": "material:m-1",
            "sequence": 3,
            "appliedSequence": -1,
            "pendingSince": db.materials.find_one({"id": "m-1"})["_id"].generation_time,
            "updatedAt": db.materials.find_one({"id": "m-1"})["_id"].generation_time,
        }
    )
    db.search_revocations.insert_one(
        {
            "_id": "material:m-1",
            "logicalKey": "material:m-1",
            "sequence": 3,
        }
    )

    assert CatalogConsumer(db, client).process_one("worker-1") is True

    assert _current_documents(db, client)["material-m-1-full"]["workingCaseIds"] == [
        "c-draft"
    ]
    assert db.search_outbox.find_one({"_id": "material:m-1"}) is None
    assert db.search_revocations.count_documents({}) == 0


def test_consumer_deletes_projection_when_source_is_no_longer_active() -> None:
    client, db = FakeMeiliClient(), database()
    _set_catalog(
        db,
        client,
        documents={
            "material-m-off-full": {"catalogId": "material-m-off-full"},
            "material-m-off-restricted": {"catalogId": "material-m-off-restricted"},
        },
    )
    db.search_outbox.insert_one(
        {
            "_id": "material:m-off",
            "sequence": 2,
            "appliedSequence": -1,
            "pendingSince": db.materials.find_one({"id": "m-off"})[
                "_id"
            ].generation_time,
            "updatedAt": db.materials.find_one({"id": "m-off"})["_id"].generation_time,
        }
    )

    assert CatalogConsumer(db, client).process_one("worker-1") is True

    assert not _current_documents(db, client)


def test_consumer_does_not_ack_or_skip_an_unknown_logical_key() -> None:
    client, db = FakeMeiliClient(), database()
    _set_catalog(db, client)
    db.search_outbox.insert_one(
        {
            "_id": "unknown:row-1",
            "sequence": 1,
            "appliedSequence": -1,
            "pendingSince": db.materials.find_one({"id": "m-1"})["_id"].generation_time,
            "updatedAt": db.materials.find_one({"id": "m-1"})["_id"].generation_time,
        }
    )

    with pytest.raises(ValueError, match="unsupported catalog logical key"):
        CatalogConsumer(db, client).process_one("worker-1")

    assert db.search_outbox.find_one({"_id": "unknown:row-1"})["appliedSequence"] == -1


def test_consumer_repairs_projection_when_new_sequence_arrives_during_write() -> None:
    client, db = FakeMeiliClient(), database()
    _set_catalog(db, client)
    queue = db.search_outbox
    queue.insert_one(
        {
            "_id": "material:m-1",
            "sequence": 3,
            "appliedSequence": -1,
            "pendingSince": db.materials.find_one()["_id"].generation_time,
            "updatedAt": db.materials.find_one()["_id"].generation_time,
        }
    )

    def update_truth() -> None:
        db.materials.update_one({"id": "m-1"}, {"$set": {"title": "最新素材"}})
        queue.update_one({"_id": "material:m-1"}, {"$set": {"sequence": 4}})

    client.after_add = update_truth
    consumer = CatalogConsumer(db, client)
    assert consumer.process_one("worker-1") is True
    assert consumer.process_one("worker-1") is True
    assert _current_documents(db, client)["material-m-1-full"]["title"] == "最新素材"
    assert queue.find_one({"_id": "material:m-1"}) is None


@pytest.mark.parametrize("final_status", ["active", "disabled"])
def test_lost_lease_converges_through_n_plus_two(final_status: str) -> None:
    client, db = FakeMeiliClient(), database()
    _set_catalog(db, client)
    _schedule_interleave(db, client, final_status)
    consumer = CatalogConsumer(db, client)

    assert consumer.process_one("worker-1") is True
    assert consumer.process_one("worker-3") is True
    assert consumer.process_one("worker-4") is True

    full = _current_documents(db, client).get("material-m-1-full")
    assert (full and full["title"]) == (
        "最终素材" if final_status == "active" else None
    )
    assert db.search_outbox.find_one({"_id": "material:m-1"}) is None
    assert db.search_revocations.count_documents({}) == 0


def test_lease_loss_during_complete_converges_without_acknowledging() -> None:
    client, db = FakeMeiliClient(), database()
    _set_catalog(db, client)
    queue = SearchOutbox(db)
    _record_material(queue)

    db.client.start_session = lambda: _interleaved_session(db, queue)
    consumer = CatalogConsumer(db, client)

    assert consumer.process_one("worker-1") is True
    db.client.start_session = lambda: PassthroughSession()
    assert consumer.process_one("worker-2") is True

    full = _current_documents(db, client)["material-m-1-full"]
    assert full["title"] == "事务竞态素材"
    assert db.search_outbox.find_one({"_id": "material:m-1"}) is None


def test_late_old_write_fails_closed_then_replay_removes_it(tmp_path) -> None:
    client, db = FakeMeiliClient(), database()
    queue = _pending_material(db, client)
    client.before_add = lambda _uid: _revoke_during_old_write(db, client, queue)
    assert CatalogConsumer(db, client).process_one("worker-old") is True
    assert "material-m-1-full" in _current_documents(db, client)
    secret = _cursor_secret(tmp_path)
    with pytest.raises(SearchUnavailable, match="同步"):
        _search_materials(db, client, secret)

    assert CatalogConsumer(db, client).process_one("worker-heal") is True
    assert _search_materials(db, client, secret)["items"] == []
    assert db.search_outbox.find_one({"_id": "material:m-1"}) is None


def test_sink_crash_leaves_pending_claim_for_expiry_replay(tmp_path) -> None:
    client, db = FakeMeiliClient(), database()
    _pending_material(db, client)

    def crash_after_write() -> None:
        raise RuntimeError("worker crashed")

    client.after_add = crash_after_write
    with pytest.raises(RuntimeError, match="worker crashed"):
        CatalogConsumer(db, client).process_one("worker-crash")
    row = db.search_outbox.find_one({"_id": "material:m-1"})
    assert row["appliedSequence"] == -1
    secret = _cursor_secret(tmp_path)
    with pytest.raises(SearchUnavailable, match="同步"):
        _search_materials(db, client, secret)

    _expire_claim(db)
    assert CatalogConsumer(db, client).process_one("worker-replay") is True
    assert _search_materials(db, client, secret)["items"][0]["id"] == "m-1"


def test_renew_failure_does_not_submit_a_sink_task(monkeypatch) -> None:
    client, db = FakeMeiliClient(), database()
    _set_catalog(db, client)
    queue = SearchOutbox(db)
    _record_material(queue)
    consumer = CatalogConsumer(db, client)
    monkeypatch.setattr(consumer.outbox, "renew", lambda _claim: False)

    assert consumer.process_one("worker-lost") is True

    assert client.tasks == 0
    assert _current_documents(db, client) == {}
    assert queue.claim("worker-next") is not None


def test_truth_load_crosses_old_lease_window_after_renewal(monkeypatch) -> None:
    client, db, clock = FakeMeiliClient(), database(), Clock()
    _set_catalog(db, client)
    queue = SearchOutbox(db, clock)
    _record_material(queue)
    original = search_worker.catalog_change

    def slow_truth(database, logical_key):
        change = original(database, logical_key)
        clock.advance(31)
        return change

    client.before_wait = lambda: clock.advance(30)
    monkeypatch.setattr(search_worker, "catalog_change", slow_truth)
    assert CatalogConsumer(db, client, clock).process_one("worker-slow") is True
    assert db.search_outbox.find_one({"_id": "material:m-1"}) is None


def test_consumer_leaves_pending_event_unclaimed_during_rebuild() -> None:
    client, db = FakeMeiliClient(), database()
    _set_catalog(db, client)
    timestamp = db.materials.find_one()["_id"].generation_time
    db.search_outbox.insert_one(
        {
            "_id": "case:c-public",
            "sequence": 1,
            "appliedSequence": -1,
            "pendingSince": timestamp,
            "updatedAt": timestamp,
        }
    )
    SearchOutbox(db).pause("active")

    assert CatalogConsumer(db, client).process_one("worker-1") is False

    assert "leaseToken" not in db.search_outbox.find_one({"_id": "case:c-public"})


def _schedule_delayed_old_write(db, client) -> None:
    _set_catalog(db, client)
    queue = SearchOutbox(db)
    _record_material(queue)

    def rebuild_after_lease_expires(_uid: str) -> None:
        _expire_claim(db)
        _set_material(db, "重建后的素材", "active")
        _rebuilder(db, client, "catalog-new").rebuild()

    client.before_add = rebuild_after_lease_expires


def test_delayed_old_worker_write_cannot_pollute_rebuilt_generation() -> None:
    client, db = FakeMeiliClient(), database()
    _schedule_delayed_old_write(db, client)
    consumer = CatalogConsumer(db, client)

    assert consumer.process_one("worker-old") is True

    marker = db.search_catalog_generation.find_one({"_id": "catalog"})
    current = client.documents[marker["indexUid"]]["material-m-1-full"]
    assert current["title"] == "重建后的素材"
    assert marker["retiredIndexUids"] == ["catalog-old"]
    assert "catalog-old" in client.documents

    assert CatalogConsumer(db, client).process_one("worker-next") is True

    assert "catalog-old" not in client.documents


def test_retired_cleanup_is_rate_limited_between_idle_worker_polls() -> None:
    client, db, clock = FakeMeiliClient(), database(), Clock()
    _set_catalog(db, client)
    db.search_catalog_generation.update_one(
        {"_id": "catalog"},
        {"$set": {"retiredIndexUids": ["retired"]}},
    )
    client.documents["retired"] = {}
    queue = SearchOutbox(db, clock)
    queue.pause("active-rebuild")
    consumer = CatalogConsumer(db, client, clock=clock)
    assert consumer.process_one("worker") is False
    client.documents["retired"] = {}
    assert consumer.process_one("worker") is False
    assert "retired" in client.documents
    clock.advance(29)
    assert queue.renew_pause("active-rebuild") is True
    clock.advance(1)
    assert consumer.process_one("worker") is False
    assert "retired" not in client.documents


def test_convergence_stops_when_rebuild_pauses_catalog_writes() -> None:
    client, db = FakeMeiliClient(), database()
    _set_catalog(db, client)
    queue = SearchOutbox(db)
    _record_material(queue)

    def pause_after_write() -> None:
        queue.pause("rebuild-active")
        _set_material(db, "暂停后的素材", "active")
        _record_material(queue)

    client.after_add = pause_after_write
    assert CatalogConsumer(db, client).process_one("worker-1") is True

    material = client.documents["catalog-old"]["material-m-1-full"]
    assert material["title"] == "素材"


def test_worker_heartbeat_records_liveness() -> None:
    db = database()

    WorkerHeartbeat(db, "worker-1").pulse()

    row = db.search_worker_state.find_one({"_id": "catalog"})
    assert row["worker"] == "worker-1"
    assert row["updatedAt"] is not None


def test_worker_heartbeat_retries_only_mongo_failures(monkeypatch) -> None:
    heartbeat = WorkerHeartbeat(database(), "worker-1")
    outcomes = iter((PyMongoError("transient"), None, RuntimeError("fatal")))
    calls = []

    def pulse() -> None:
        calls.append(len(calls) + 1)
        error = next(outcomes)
        if error:
            raise error

    monkeypatch.setattr("app.modules.search.worker.time.sleep", lambda _delay: None)
    monkeypatch.setattr(heartbeat, "pulse", pulse)
    with pytest.raises(RuntimeError, match="fatal"):
        heartbeat.run()
    assert calls == [1, 2, 3]
