from __future__ import annotations

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from app.core.config import Settings


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
    database.case_versions.create_index([("id", ASCENDING)], unique=True)
    database.case_versions.create_index(
        [("caseId", ASCENDING), ("number", ASCENDING)], unique=True
    )
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


def initialize(database: Database) -> None:
    database.client.admin.command("ping")
    _initialize_auth(database)
    _initialize_cases(database)
    _initialize_history(database)
    _initialize_case_assets(database)
    _initialize_materials(database)
    _initialize_knowledge(database)
    _initialize_search_delivery(database)
