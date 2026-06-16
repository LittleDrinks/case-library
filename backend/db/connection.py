"""MongoDB connection and index initialization."""

from __future__ import annotations

from pymongo import ASCENDING, DESCENDING, TEXT, MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from db.constants import MONGODB_DB_NAME, MONGODB_TIMEOUT_MS, MONGODB_URI

_client: MongoClient | None = None

def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=MONGODB_TIMEOUT_MS)
    return _client

def get_db_connection():
    """Compatibility wrapper: return the MongoDB database object."""
    return get_mongo_client()[MONGODB_DB_NAME]

def get_db():
    return get_db_connection()


def init_db():
    """Initialize MongoDB indexes. This never drops data."""
    from repositories.cases import backfill_owner_username

    from db.counters import sync_all_counters

    try:
        client = get_mongo_client()
        client.admin.command("ping")
    except ServerSelectionTimeoutError as exc:
        raise RuntimeError(
            f"Cannot connect to MongoDB at {MONGODB_URI}. "
            "Start MongoDB or set MONGODB_URI correctly."
        ) from exc

    db = get_db()
    db.users.create_index([("id", ASCENDING)], unique=True)
    db.users.create_index([("username", ASCENDING)], unique=True)
    db.users.create_index([("role", ASCENDING), ("status", ASCENDING)])
    token_repair = db.users.update_many(
        {"token_version": {"$exists": False}}, {"$set": {"token_version": 0}}
    )
    if token_repair.modified_count:
        print(f"Backfilled token_version on {token_repair.modified_count} legacy user(s)")

    db.cases.create_index([("id", ASCENDING)], unique=True)
    db.cases.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    db.cases.create_index(
        [("author", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)]
    )
    db.cases.create_index(
        [("owner_username", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)]
    )
    db.cases.create_index([("type", ASCENDING), ("theme", ASCENDING)])
    existing_text_index = db.cases.index_information().get("cases_text_idx")
    existing_weights = (existing_text_index or {}).get("weights", {})
    if existing_text_index and "source_material" not in existing_weights:
        db.cases.drop_index("cases_text_idx")
    db.cases.create_index(
        [("title", TEXT), ("content", TEXT), ("source_material", TEXT), ("keywords", TEXT)],
        name="cases_text_idx",
        default_language="none",
    )

    db.reviews.create_index([("id", ASCENDING)], unique=True)
    db.reviews.create_index([("case_id", ASCENDING), ("review_at", DESCENDING)])
    db.versions.create_index([("id", ASCENDING)], unique=True)
    db.versions.create_index([("case_id", ASCENDING), ("version_number", DESCENDING)])
    db.deployments.create_index([("id", ASCENDING)], unique=True)
    db.deployments.create_index([("case_id", ASCENDING), ("deployed_at", DESCENDING)])

    sync_all_counters()
    repair = backfill_owner_username()
    if repair["fixed"]:
        print(f"Backfilled owner_username on {repair['fixed']} legacy case(s)")
    print(f"MongoDB initialized: {MONGODB_URI}/{MONGODB_DB_NAME}")
