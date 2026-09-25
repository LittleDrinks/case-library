from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from time import monotonic, sleep
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.core.config import Settings


def _ensure_agent_artifact_indexes(database: Database) -> None:
    migration_id = "agent-artifact-index-v1"
    migrations = database.schema_migrations
    owner = uuid4().hex
    deadline = monotonic() + 660
    while True:
        if migrations.find_one(
            {"_id": migration_id, "completedAt": {"$exists": True}}, {"_id": 1}
        ):
            return
        now = datetime.now(UTC)
        try:
            claim = migrations.find_one_and_update(
                {"_id": migration_id, "completedAt": {"$exists": False},
                 "$or": [{"leaseUntil": {"$lte": now}},
                         {"leaseUntil": {"$exists": False}}]},
                {"$set": {"owner": owner, "leaseUntil": now + timedelta(minutes=10)}},
                upsert=True, return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            claim = None
        if claim and claim.get("owner") == owner:
            lease_lost = Event()
            stop_renewal = Event()

            def renew_lease() -> None:
                while not stop_renewal.wait(30):
                    try:
                        result = migrations.update_one(
                            {"_id": migration_id, "owner": owner,
                             "completedAt": {"$exists": False}},
                            {"$set": {"leaseUntil": datetime.now(UTC)
                                      + timedelta(minutes=10)}},
                        )
                    except Exception:
                        lease_lost.set()
                        return
                    if result.matched_count != 1:
                        lease_lost.set()
                        return

            renewal = Thread(target=renew_lease, daemon=True)
            renewal.start()
            try:
                _renew_agent_artifact_lease(migrations, migration_id, owner, lease_lost)
                _replace_index(database.case_versions, "one_ai_version_per_run",
                               [("caseId", ASCENDING), ("sourceRunId", ASCENDING)],
                               unique=True, partial_filter={
                                   "sourceRunId": {"$type": "string"},
                                   "sourceArtifactId": {"$exists": False},
                               })
                _renew_agent_artifact_lease(migrations, migration_id, owner, lease_lost)
                _replace_index(database.case_versions, "one_ai_version_per_artifact",
                               [("sourceArtifactId", ASCENDING)], unique=True,
                               partial_filter={"sourceArtifactId": {"$type": "string"}})
                _renew_agent_artifact_lease(migrations, migration_id, owner, lease_lost)
                _replace_index(database.agent_writes, "runId_1", [("runId", ASCENDING)],
                               unique=True,
                               partial_filter={"artifactId": {"$exists": False}})
                _renew_agent_artifact_lease(migrations, migration_id, owner, lease_lost)
                _replace_index(database.agent_writes, "one_write_per_artifact",
                               [("artifactId", ASCENDING)], unique=True,
                               partial_filter={"artifactId": {"$type": "string"}})
                if lease_lost.is_set():
                    raise RuntimeError("agent artifact index migration lease lost")
                completed = migrations.update_one(
                    {"_id": migration_id, "owner": owner,
                     "completedAt": {"$exists": False}},
                    {"$set": {"completedAt": datetime.now(UTC)},
                     "$unset": {"owner": "", "leaseUntil": ""}},
                )
                if completed.matched_count != 1:
                    raise RuntimeError("agent artifact index migration lease lost")
            except Exception:
                stop_renewal.set()
                renewal.join()
                migrations.update_one(
                    {"_id": migration_id, "owner": owner},
                    {"$unset": {"owner": "", "leaseUntil": ""}},
                )
                raise
            stop_renewal.set()
            renewal.join()
            return
        if monotonic() >= deadline:
            raise RuntimeError("agent artifact index migration did not finish")
        sleep(0.05)


def _renew_agent_artifact_lease(migrations, migration_id, owner, lease_lost) -> None:
    if lease_lost.is_set():
        raise RuntimeError("agent artifact index migration lease lost")
    result = migrations.update_one(
        {"_id": migration_id, "owner": owner, "completedAt": {"$exists": False}},
        {"$set": {"leaseUntil": datetime.now(UTC) + timedelta(minutes=10)}},
    )
    if result.matched_count != 1:
        lease_lost.set()
        raise RuntimeError("agent artifact index migration lease lost")


def _replace_index(collection, name, keys, *, unique, partial_filter) -> None:
    existing = collection.index_information().get(name)
    if existing and (
        existing.get("key") != keys
        or existing.get("unique", False) != unique
        or existing.get("partialFilterExpression") != partial_filter
    ):
        collection.drop_index(name)
    elif existing:
        return
    collection.create_index(
        keys, name=name, unique=unique, partialFilterExpression=partial_filter,
    )


def connect(settings: Settings) -> tuple[MongoClient, Database]:
    client = MongoClient(
        settings.mongo_uri,
        serverSelectionTimeoutMS=settings.mongo_timeout_ms,
        maxPoolSize=settings.mongo_max_pool_size,
        tz_aware=True,
        retryReads=True,
        retryWrites=True,
        w="majority",
    )
    return client, client[settings.mongo_database]


def _initialize_auth(database: Database) -> None:
    database.users.create_index([("id", ASCENDING)], unique=True)
    database.users.create_index([("username", ASCENDING)], unique=True)
    database.sessions.create_index([("token_hash", ASCENDING)], unique=True)
    database.sessions.create_index("expires_at", expireAfterSeconds=0)
    database.ai_usage.create_index("expiresAt", expireAfterSeconds=0)


def _initialize_cases(database: Database) -> None:
    database.cases.create_index([("id", ASCENDING)], unique=True)
    database.cases.create_index([("ownerId", ASCENDING), ("updatedAt", ASCENDING)])
    database.cases.create_index(
        [("publicationStatus", ASCENDING), ("publishedAt", ASCENDING)]
    )
    database.cases.create_index(
        [("publishedVersionId", ASCENDING), ("publicationStatus", ASCENDING)]
    )
    _initialize_case_versions(database)


def _initialize_case_versions(database: Database) -> None:
    database.case_versions.create_index([("id", ASCENDING)], unique=True)
    database.case_versions.create_index(
        [("caseId", ASCENDING), ("number", ASCENDING)], unique=True
    )
    _replace_index(database.case_versions, "one_ai_version_per_run",
                   [("caseId", ASCENDING), ("sourceRunId", ASCENDING)],
                   unique=True, partial_filter={
                       "sourceRunId": {"$type": "string"},
                       "sourceArtifactId": {"$exists": False},
                   })
    _replace_index(database.case_versions, "one_ai_version_per_artifact",
                   [("sourceArtifactId", ASCENDING)], unique=True,
                   partial_filter={"sourceArtifactId": {"$type": "string"}})
    database.case_versions.create_index([("attachments.blobId", ASCENDING)])
    database.case_versions.create_index([("materials.id", ASCENDING)])


def _initialize_history(database: Database) -> None:
    database.case_snapshots.create_index([("id", ASCENDING)], unique=True)
    database.case_snapshots.create_index(
        [("caseId", ASCENDING), ("createdAt", ASCENDING)]
    )
    database.case_snapshots.create_index([("attachments.blobId", ASCENDING)])
    database.lifecycle_events.create_index(
        [("caseId", ASCENDING), ("createdAt", ASCENDING)]
    )


def _initialize_case_assets(database: Database) -> None:
    database.attachments.create_index([("id", ASCENDING)], unique=True)
    database.attachments.create_index([("caseId", ASCENDING), ("createdAt", ASCENDING)])
    database.annotations.create_index([("id", ASCENDING)], unique=True)
    database.annotations.create_index(
        [("caseId", ASCENDING), ("versionId", ASCENDING), ("createdAt", ASCENDING)]
    )
    database.case_materials.create_index(
        [("caseId", ASCENDING), ("materialId", ASCENDING)], unique=True
    )
    database.case_materials.create_index(
        [("materialId", ASCENDING), ("caseId", ASCENDING)]
    )
    database.case_sources.create_index([("id", ASCENDING)], unique=True)
    database.case_sources.create_index([("caseId", ASCENDING), ("createdAt", ASCENDING)])
    database.case_sources.create_index(
        [("caseId", ASCENDING), ("sourceCaseId", ASCENDING), ("versionId", ASCENDING)],
        unique=True,
    )


def _initialize_materials(database: Database) -> None:
    database.materials.create_index([("id", ASCENDING)], unique=True)
    database.materials.create_index([("status", ASCENDING), ("accessLevel", ASCENDING)])
    database.material_import_jobs.create_index([("id", ASCENDING)], unique=True)
    database.material_import_items.create_index([("id", ASCENDING)], unique=True)
    database.material_import_items.create_index(
        [("jobId", ASCENDING), ("order", ASCENDING)], unique=True
    )
    database.material_candidates.create_index([("id", ASCENDING)], unique=True)
    database.material_candidates.create_index([("sha256", ASCENDING)], unique=True)
    database.material_candidates.create_index(
        [
            ("status", ASCENDING),
            ("createdAt", DESCENDING),
            ("id", DESCENDING),
        ]
    )


def _initialize_knowledge(database: Database) -> None:
    database.knowledge_sources.create_index([("id", ASCENDING)], unique=True)
    database.knowledge_chapters.create_index([("id", ASCENDING)], unique=True)
    database.knowledge_chapters.create_index(
        [("sourceId", ASCENDING), ("index", ASCENDING)], unique=True
    )
    database.knowledge_sections.create_index([("id", ASCENDING)], unique=True)
    database.knowledge_sections.create_index(
        [("sourceId", ASCENDING), ("chapterId", ASCENDING), ("index", ASCENDING)],
        unique=True,
    )


def _initialize_tags(database: Database) -> None:
    database.tag_groups.create_index([("id", ASCENDING)], unique=True)
    database.tag_groups.create_index([("name", ASCENDING)], unique=True)
    database.tags.create_index([("id", ASCENDING)], unique=True)
    database.tags.create_index(
        [("groupId", ASCENDING), ("name", ASCENDING)], unique=True
    )
    database.cases.create_index("tagIds")
    database.case_versions.create_index("metadata.tagIds")


def _initialize_search_delivery(database: Database) -> None:
    database.search_outbox.create_index(
        [
            ("updatedAt", ASCENDING),
            ("_id", ASCENDING),
        ]
    )
    database.search_outbox.create_index(
        [
            ("pendingSince", ASCENDING),
            ("_id", ASCENDING),
        ]
    )
    database.search_revocations.create_index(
        [("logicalKey", ASCENDING)],
        unique=True,
    )


def _initialize_agent_threads(database: Database) -> None:
    information = database.agent_threads.index_information()
    for legacy in ("ownerId_1_caseId_1_isDefault_1", "agent_one_default_thread"):
        if legacy in information:
            database.agent_threads.drop_index(legacy)
    database.agent_threads.create_index([("id", ASCENDING)], unique=True)
    # mode 参与唯一性：同一管理员的作者线程（mode 缺省）与审核线程（mode=review）互不冲突。
    database.agent_threads.create_index(
        [("ownerId", ASCENDING), ("caseId", ASCENDING), ("versionId", ASCENDING),
         ("mode", ASCENDING)],
        unique=True,
        partialFilterExpression={"isDefault": True},
        name="agent_one_default_thread",
    )
    database.agent_threads.create_index(
        [("ownerId", ASCENDING), ("caseId", ASCENDING), ("updatedAt", DESCENDING)]
    )


def _initialize_agent_messages(database: Database) -> None:
    database.agent_messages.create_index([("id", ASCENDING)], unique=True)
    database.agent_messages.create_index(
        [("threadId", ASCENDING), ("messageSeq", ASCENDING)], unique=True
    )


def _initialize_skills(database: Database) -> None:
    database.skills.create_index([("id", ASCENDING)], unique=True)
    database.skill_versions.create_index([("id", ASCENDING)], unique=True)
    database.skill_versions.create_index(
        [("skillId", ASCENDING), ("version", ASCENDING)], unique=True
    )


def _initialize_agent_runs(database: Database) -> None:
    database.agent_runs.create_index([("id", ASCENDING)], unique=True)
    database.agent_runs.create_index(
        [("threadId", ASCENDING), ("startedAt", DESCENDING), ("id", DESCENDING)]
    )
    database.agent_runs.create_index(
        [("threadId", ASCENDING), ("status", ASCENDING)],
        unique=True,
        partialFilterExpression={"status": "active"},
        name="agent_one_active_run_per_thread",
    )
    database.agent_runs.create_index(
        [("threadId", ASCENDING), ("clientRequestId", ASCENDING)],
        unique=True,
        partialFilterExpression={"clientRequestId": {"$type": "string"}},
        name="agent_one_run_per_client_request",
    )
    _initialize_agent_run_quota_index(database)


def _initialize_agent_run_quota_index(database: Database) -> None:
    database.agent_runs.create_index(
        [("status", ASCENDING), ("quotaIds", ASCENDING), ("ownerExpiresAt", ASCENDING)]
    )


def _initialize_agent_events(database: Database) -> None:
    database.agent_thread_events.create_index([("id", ASCENDING)], unique=True)
    database.agent_thread_events.create_index(
        [("threadId", ASCENDING), ("eventSeq", ASCENDING)], unique=True
    )


def _initialize_agent_artifacts(database: Database) -> None:
    database.agent_artifacts.create_index([("id", ASCENDING)], unique=True)
    database.agent_artifacts.create_index(
        [("threadId", ASCENDING), ("createdAt", ASCENDING)]
    )
    database.agent_artifacts.create_index(
        [("caseId", ASCENDING), ("status", ASCENDING)]
    )


def _initialize_agent_writes(database: Database) -> None:
    database.agent_writes.create_index([("id", ASCENDING)], unique=True)
    _replace_index(database.agent_writes, "runId_1", [("runId", ASCENDING)],
                   unique=True, partial_filter={"artifactId": {"$exists": False}})
    _replace_index(database.agent_writes, "one_write_per_artifact",
                   [("artifactId", ASCENDING)], unique=True,
                   partial_filter={"artifactId": {"$type": "string"}})
    database.agent_writes.create_index(
        [("threadId", ASCENDING), ("createdAt", ASCENDING)]
    )


def _initialize_agent(database: Database) -> None:
    _initialize_agent_threads(database)
    _initialize_agent_messages(database)
    _initialize_agent_runs(database)
    _initialize_agent_events(database)
    _initialize_agent_artifacts(database)
    _initialize_agent_writes(database)


def initialize(database: Database) -> None:
    database.client.admin.command("ping")
    _ensure_agent_artifact_indexes(database)
    _initialize_auth(database)
    _initialize_cases(database)
    _initialize_history(database)
    _initialize_case_assets(database)
    _initialize_materials(database)
    _initialize_knowledge(database)
    _initialize_tags(database)
    _initialize_search_delivery(database)
    _initialize_agent(database)
    _initialize_skills(database)
