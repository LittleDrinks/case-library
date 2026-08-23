from __future__ import annotations

import uuid
import time
from collections import defaultdict
from collections.abc import Callable, Iterable

from pymongo.database import Database

from app.modules.search.client import index_epoch, wait_task
from app.modules.search.outbox import SearchOutbox
from app.modules.search.projection import project_catalog_documents

BATCH_SIZE = 500
FILTERABLE = (
    "catalogId",
    "id",
    "docClass",
    "kind",
    "typeName",
    "audience",
    "tags",
    "publishedAt",
    "authority",
    "materialType",
    "accessLevel",
    "createdBy",
    "publicReferenceCount",
    "workingCaseIds",
    "publishedVersionIds",
)
SORTABLE = ("publishedAt", "title", "kind", "id")
SEARCHABLE = ("title", "searchableText")
DISPLAYED = (
    "catalogId",
    "id",
    "kind",
    "docClass",
    "title",
    "summary",
    "publishedAt",
    "typeId",
    "typeName",
    "course",
    "author",
    "organization",
    "stageText",
    "audience",
    "purpose",
    "likes",
    "theoryPoints",
    "tags",
    "knowledgeLevel",
    "edition",
    "chapterCount",
    "sectionCount",
    "sourceId",
    "chapterId",
    "chapter",
    "index",
    "unit",
    "excerpt",
    "source",
    "sourceUrl",
    "materialType",
    "authority",
    "accessLevel",
    "status",
    "createdBy",
    "publicReferenceCount",
    "citedCount",
    "filename",
    "mediaType",
    "size",
    "hasFile",
    "workingCaseIds",
    "publishedVersionIds",
    "generation",
)


def catalog_settings() -> dict:
    return {
        "filterableAttributes": list(FILTERABLE),
        "sortableAttributes": list(SORTABLE),
        "searchableAttributes": list(SEARCHABLE),
        "displayedAttributes": list(DISPLAYED),
        "pagination": {"maxTotalHits": 25_000},
    }


def _chunks(rows: Iterable[dict]) -> Iterable[list[dict]]:
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) == BATCH_SIZE:
            yield batch
            batch = []
    if batch:
        yield batch


def _missing(error: Exception) -> bool:
    code = getattr(error, "code", getattr(error, "error_code", ""))
    return code == "index_not_found" or "index_not_found" in str(error)


def _index_exists(client, uid: str) -> bool:
    try:
        client.get_index(uid)
        return True
    except Exception as error:
        if _missing(error):
            return False
        raise


def _create_index(client, uid: str) -> None:
    wait_task(client, client.create_index(uid, {"primaryKey": "catalogId"}))


def _delete_index(client, uid: str) -> None:
    if _index_exists(client, uid):
        wait_task(client, client.delete_index(uid))


def cleanup_retired_indexes(database: Database, client) -> None:
    marker = database.search_catalog_generation.find_one({"_id": "catalog"})
    if not marker:
        return
    for uid in marker["retiredIndexUids"]:
        if uid == marker["indexUid"]:
            continue
        try:
            _delete_index(client, uid)
        except Exception:
            continue


def _case_documents(database: Database) -> Iterable[dict]:
    for case in database.cases.find({"publicationStatus": "public"}):
        query = {"id": case.get("publishedVersionId"), "caseId": case["id"]}
        version = database.case_versions.find_one(query)
        if not version:
            raise RuntimeError(f"公开案例缺少发布版本: {case['id']}")
        yield from project_catalog_documents("case", version, case)


def _active_sources(database: Database) -> list[dict]:
    return list(database.knowledge_sources.find({"status": "active"}))


def _knowledge_documents(database: Database) -> Iterable[dict]:
    sources = _active_sources(database)
    for source in sources:
        yield from project_catalog_documents("knowledge_source", source)
    source_ids = [source["id"] for source in sources]
    for section in database.knowledge_sections.find({"sourceId": {"$in": source_ids}}):
        yield from project_catalog_documents("knowledge_section", section)


def _working_mounts(database: Database) -> dict[str, set[str]]:
    result = defaultdict(set)
    for row in database.case_materials.find({}, {"materialId": 1, "caseId": 1}):
        result[row["materialId"]].add(row["caseId"])
    return result


def _published_mounts(database: Database) -> dict[str, set[str]]:
    result = defaultdict(set)
    public = database.cases.find({"publicationStatus": "public"})
    version_ids = [case["publishedVersionId"] for case in public]
    for version in database.case_versions.find({"id": {"$in": version_ids}}):
        for material in version.get("materials", []):
            result[material["id"]].add(version["id"])
    return result


def material_context(database: Database, material_id: str) -> dict:
    working = database.case_materials.distinct("caseId", {"materialId": material_id})
    query = {"publicationStatus": "public"}
    version_ids = [row["publishedVersionId"] for row in database.cases.find(query)]
    published = database.case_versions.distinct(
        "id",
        {"id": {"$in": version_ids}, "materials.id": material_id},
    )
    return {"workingCaseIds": sorted(working), "publishedVersionIds": sorted(published)}


def _material_documents(database: Database) -> Iterable[dict]:
    working, published = _working_mounts(database), _published_mounts(database)
    for material in database.materials.find({"status": "active"}):
        context = {
            "workingCaseIds": sorted(working[material["id"]]),
            "publishedVersionIds": sorted(published[material["id"]]),
        }
        yield from project_catalog_documents("material", material, context)


def catalog_documents(database: Database) -> Iterable[dict]:
    yield from _case_documents(database)
    yield from _knowledge_documents(database)
    yield from _material_documents(database)


def _generation_document(generation: str) -> dict:
    return {
        "catalogId": "catalog-meta",
        "docClass": "catalog-meta",
        "generation": generation,
    }


class CatalogRebuilder:
    def __init__(
        self,
        database: Database,
        client,
        index_prefix: str,
        build_uid: Callable[[], str] | None = None,
        clock=None,
    ) -> None:
        self.database, self.client, self.index_prefix = database, client, index_prefix
        self.outbox = (
            SearchOutbox(database) if clock is None else SearchOutbox(database, clock)
        )
        self._build_uid = build_uid or self._new_build_uid

    def _new_build_uid(self) -> str:
        return f"{self.index_prefix}-generation-{uuid.uuid4().hex}"

    def _renew(self, owner: str) -> None:
        if not self.outbox.renew_pause(owner):
            raise RuntimeError("重建租约已失效")

    def _add(self, index, documents: list[dict], owner: str) -> None:
        self._renew(owner)
        task = index.add_documents(documents, primary_key="catalogId")
        wait_task(self.client, task)
        self._renew(owner)

    def _load(self, uid: str, generation: str, owner: str) -> int:
        count, index = 0, self.client.index(uid)
        self._add(index, [_generation_document(generation)], owner)
        for batch in _chunks(catalog_documents(self.database)):
            self._add(index, batch, owner)
            count += len(batch)
        return count

    def _prepare(self, uid: str, owner: str) -> None:
        self._renew(owner)
        _delete_index(self.client, uid)
        self._renew(owner)
        _create_index(self.client, uid)
        self._renew(owner)
        wait_task(
            self.client, self.client.index(uid).update_settings(catalog_settings())
        )
        self._renew(owner)

    def _wait_for_consumers(self, owner: str) -> None:
        self._renew(owner)
        while self.outbox.has_active_claims():
            time.sleep(1)
            self._renew(owner)

    def _generation_marker(self, generation: str, uid: str) -> dict:
        previous = self.database.search_catalog_generation.find_one({"_id": "catalog"})
        retired = set(previous["retiredIndexUids"]) if previous else set()
        if previous and previous["indexUid"] != uid:
            retired.add(previous["indexUid"])
        retired.discard(uid)
        return {
            "_id": "catalog",
            "generation": generation,
            "indexUid": uid,
            "indexEpoch": index_epoch(self.client, uid),
            "retiredIndexUids": sorted(retired),
        }

    def _publish_generation(self, generation: str, uid: str) -> None:
        marker = self._generation_marker(generation, uid)
        if not self.outbox.publish(generation, marker):
            raise RuntimeError("重建租约已失效")

    def _finish(self, uid: str, published: bool) -> None:
        if published:
            cleanup_retired_indexes(self.database, self.client)
            return
        _delete_index(self.client, uid)

    def rebuild(self) -> int:
        uid, token, published = self._build_uid(), uuid.uuid4().hex, False
        with self.outbox.rebuild_lease(token) as lease:
            try:
                self._wait_for_consumers(token)
                self._prepare(uid, token)
                count = self._load(uid, token, token)
                lease.finish()
                self._publish_generation(token, uid)
                published = True
                return count
            finally:
                self._finish(uid, published)
