from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.modules.search.client import index_epoch, wait_task
from app.modules.search.indexer import cleanup_retired_indexes, material_context
from app.modules.search.outbox import CatalogTarget, OutboxClaim, SearchOutbox
from app.modules.search.projection import case_catalog_ids, project_catalog_documents

RETIRED_CLEANUP_INTERVAL = timedelta(seconds=30)
WORKER_HEARTBEAT_INTERVAL = 2


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class CatalogChange:
    documents: list[dict]
    deleted_ids: list[str]


class LostClaim(RuntimeError):
    pass


class WorkerHeartbeat:
    def __init__(self, database: Database, worker: str, clock=_now) -> None:
        self._state, self._worker, self._clock = (
            database.search_worker_state,
            worker,
            clock,
        )

    def pulse(self) -> None:
        record = {"worker": self._worker, "updatedAt": self._clock()}
        self._state.update_one({"_id": "catalog"}, {"$set": record}, upsert=True)

    def run(self) -> None:
        while True:
            time.sleep(WORKER_HEARTBEAT_INTERVAL)
            try:
                self.pulse()
            except PyMongoError:
                continue

    def start(self) -> None:
        self.pulse()
        threading.Thread(target=self.run, daemon=True).start()


def _parts(logical_key: str) -> tuple[str, str]:
    kind, separator, source_id = logical_key.partition(":")
    if not separator or not source_id:
        raise ValueError(f"unsupported catalog logical key: {logical_key}")
    return kind, source_id


def _case_change(database: Database, source_id: str) -> CatalogChange:
    case = database.cases.find_one({"id": source_id, "publicationStatus": "public"})
    if not case:
        return CatalogChange([], case_catalog_ids(source_id))
    query = {"id": case.get("publishedVersionId"), "caseId": source_id}
    version = database.case_versions.find_one(query)
    if not version:
        raise RuntimeError(f"公开案例缺少发布版本: {source_id}")
    return CatalogChange(project_catalog_documents("case", version, case), [])


def _material_change(database: Database, source_id: str) -> CatalogChange:
    material = database.materials.find_one({"id": source_id, "status": "active"})
    ids = [f"material-{source_id}-full", f"material-{source_id}-restricted"]
    if not material:
        return CatalogChange([], ids)
    context = material_context(database, source_id)
    return CatalogChange(project_catalog_documents("material", material, context), [])


def _source_change(database: Database, source_id: str) -> CatalogChange:
    source = database.knowledge_sources.find_one({"id": source_id, "status": "active"})
    if source:
        return CatalogChange(project_catalog_documents("knowledge_source", source), [])
    sections = database.knowledge_sections.distinct("id", {"sourceId": source_id})
    deleted = [f"knowledge-source-{source_id}"]
    deleted.extend(f"knowledge-section-{section_id}" for section_id in sections)
    return CatalogChange([], deleted)


def _section_change(database: Database, source_id: str) -> CatalogChange:
    section = database.knowledge_sections.find_one({"id": source_id})
    source = section and database.knowledge_sources.find_one(
        {"id": section["sourceId"], "status": "active"},
        {"_id": 1},
    )
    if not section or not source:
        return CatalogChange([], [f"knowledge-section-{source_id}"])
    return CatalogChange(project_catalog_documents("knowledge_section", section), [])


def catalog_change(database: Database, logical_key: str) -> CatalogChange:
    kind, source_id = _parts(logical_key)
    handlers = {
        "case": _case_change,
        "material": _material_change,
        "knowledge_source": _source_change,
        "knowledge_section": _section_change,
    }
    if kind not in handlers:
        raise ValueError(f"unsupported catalog logical key: {logical_key}")
    return handlers[kind](database, source_id)


class CatalogConsumer:
    def __init__(self, database: Database, client, clock=_now) -> None:
        self.database, self.client = database, client
        self.outbox = SearchOutbox(database, clock)
        self._clock = clock
        self._next_cleanup_at = datetime.min.replace(tzinfo=UTC)

    def _cleanup_retired(self) -> None:
        timestamp = self._clock()
        if timestamp < self._next_cleanup_at:
            return
        self._next_cleanup_at = timestamp + RETIRED_CLEANUP_INTERVAL
        cleanup_retired_indexes(self.database, self.client)

    def _renew(self, claim: OutboxClaim) -> None:
        if not self.outbox.renew(claim):
            raise LostClaim

    def _apply(self, claim, change, target) -> str:
        index = self.client.index(target.index_uid)
        if change.documents:
            self._renew(claim)
            task = index.add_documents(change.documents, primary_key="catalogId")
            wait_task(self.client, task)
        if change.deleted_ids:
            self._renew(claim)
            wait_task(self.client, index.delete_documents(change.deleted_ids))
        return index_epoch(self.client, target.index_uid)

    def _claim_target(self, claim: OutboxClaim) -> CatalogTarget | None:
        target = self.outbox.target()
        if target and self.outbox.current(claim) and self.outbox.writable(target):
            return target
        self.outbox.release(claim)
        return None

    def _release_if_stale(self, claim: OutboxClaim, target: CatalogTarget) -> bool:
        if self.outbox.current(claim) and self.outbox.writable(target):
            return False
        self.outbox.release(claim)
        return True

    def _finish_claim(self, claim, target, epoch) -> None:
        self._complete(claim, target, epoch)

    def process_one(self, worker: str) -> bool:
        self._cleanup_retired()
        if self.outbox.paused():
            return False
        claim = self.outbox.claim(worker)
        if not claim:
            return False
        self._process_claim(claim)
        return True

    def _process_claim(self, claim: OutboxClaim) -> None:
        target = self._claim_target(claim)
        if not target:
            return
        change = catalog_change(self.database, claim.logical_key)
        if self._release_if_stale(claim, target):
            return
        try:
            epoch = self._apply(claim, change, target)
        except LostClaim:
            self.outbox.release(claim)
            return
        self._finish_claim(claim, target, epoch)

    def _complete(self, claim, target, epoch) -> None:
        if self.outbox.complete(claim, target, epoch):
            return
        self.outbox.requeue(claim.logical_key)
        self.outbox.release(claim)


def run_worker(
    consumer: CatalogConsumer, worker: str, idle_seconds: float = 0.25
) -> None:
    while True:
        if not consumer.process_one(worker):
            time.sleep(idle_seconds)


def worker_name() -> str:
    return f"{socket.gethostname()}:{uuid4().hex[:8]}"


def uuid4():
    import uuid

    return uuid.uuid4()


def main() -> int:
    from app.core.config import Settings
    from app.core.database import connect
    from app.modules.search.client import create_client

    settings = Settings.from_environment()
    _mongo, database = connect(settings)
    client = create_client(settings.search_url, settings.search_api_key_file)
    name = worker_name()
    WorkerHeartbeat(database, name).start()
    run_worker(CatalogConsumer(database, client), name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
