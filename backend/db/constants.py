"""Shared database constants and environment configuration."""

from __future__ import annotations

import os
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "case_library")
MONGODB_TIMEOUT_MS = int(os.getenv("MONGODB_TIMEOUT_MS", "5000"))
STATISTICS_CACHE_TTL_SECONDS = int(os.getenv("STATISTICS_CACHE_TTL_SECONDS", "300"))
SQLITE_DB_PATH = os.getenv(
    "SQLITE_DB_PATH",
    str(Path(__file__).resolve().parents[2] / "data" / "cases.db"),
)

CASE_STATUSES = {
    "draft",
    "pending_review",
    "approved",
    "needs_revision",
    "deleted",
}
TARGET_STAGE_LABELS = {
    "undergraduate": "本科生",
    "master": "硕士研究生",
    "doctor": "博士研究生",
}
REVIEW_STATUSES = {"pending", "approved", "rejected", "approve", "reject", "needs_revision"}
USER_ROLES = {"normal", "admin"}
USER_STATUSES = {"active", "no_active"}
COUNTER_COLLECTIONS = ["users", "cases", "reviews", "versions", "deployments"]
MAX_QUERY_LIMIT = 100
VERSIONED_FIELDS = [
    "title",
    "type",
    "theme",
    "target_stages",
    "content",
    "source_material",
    "author",
    "department",
    "keywords",
]
PUBLIC_REVIEW_SNAPSHOT_FIELDS = [
    "title",
    "type",
    "theme",
    "target_stages",
    "content",
    "source_material",
    "author",
    "department",
    "keywords",
]
DATETIME_FIELDS = {
    "created_at",
    "updated_at",
    "submitted_at",
    "review_at",
    "deployed_at",
    "deleted_at",
}
AI_REVIEW_DATETIME_FIELDS = {"reviewed_at", "created_at"}
BEIJING_TZ = timezone(timedelta(hours=8))
