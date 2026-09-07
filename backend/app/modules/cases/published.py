from __future__ import annotations

from pymongo.database import Database

from app.modules.cases.service import CaseError

PUBLIC_METADATA_FIELDS = (
    "typeId",
    "typeName",
    "course",
    "author",
    "organization",
    "stageText",
    "audience",
    "purpose",
    "theoryPoints",
    "likes",
)


class PublishedCaseReader:
    def __init__(self, database: Database):
        self.database = database

    def get(self, case: dict) -> dict:
        version_id = case.get("publishedVersionId")
        version = self.database.case_versions.find_one(
            {"id": version_id, "caseId": case["id"]}
        )
        if not version_readable(self.database, case, version_id, version, False):
            raise CaseError(404, "案例不存在")
        return published_view(case, version)

    def read_public_version(self, case: dict, version_id: str) -> dict:
        """公共阅读固定版本：即使 admin/owner 也按读者权限判定。"""
        version = find_version(self.database, case, version_id, False)
        if not version_readable(self.database, case, version_id, version, False):
            raise CaseError(404, "案例版本不存在")
        return _published_view(case, version)


def find_version(database: Database, case: dict, version_id: str, internal: bool) -> dict | None:
    query = {"id": version_id, "caseId": case["id"]}
    version = database.case_versions.find_one(query)
    if version or not internal:
        return version
    return database.case_snapshots.find_one(query)


def version_readable(
    database: Database,
    case: dict,
    version_id: str,
    version: dict | None,
    internal: bool,
) -> bool:
    """已批准历史版本对普通读者可读；草稿与快照仅内部可见。"""
    if internal:
        return version is not None
    if case.get("publicationStatus") != "public" or version is None:
        return False
    if version_id == case.get("publishedVersionId"):
        return True
    approved = database.lifecycle_events.find_one(
        {"caseId": case["id"], "action": "approve", "versionId": version_id},
        {"_id": 1},
    )
    return bool(approved)


def version_readable(
    database: Database, case: dict, version_id: str, version: dict | None,
    internal: bool, session=None,
) -> bool:
    """已发布历史版本对普通读者可读；草稿与快照仅内部可见。"""
    if internal:
        return version is not None
    if case.get("publicationStatus") != "public" or version is None:
        return False
    if version_id == case.get("publishedVersionId"):
        return True
    approved = database.lifecycle_events.find_one(
        {"caseId": case["id"], "action": "approve", "versionId": version_id},
        {"_id": 1},
        session=session,
    )
    return bool(approved)


def version_readable_by_id(database: Database, case_id: str, version_id: str | None) -> bool:
    if not version_id:
        return False
    case = database.cases.find_one({"id": case_id})
    version = database.case_versions.find_one({"id": version_id, "caseId": case_id})
    return bool(
        case and version and version_readable(database, case, version_id, version, False)
    )


def published_view(case: dict, version: dict) -> dict:
    metadata = {field: version["metadata"].get(field) for field in PUBLIC_METADATA_FIELDS}
    return {
        **metadata,
        "id": case["id"],
        "versionId": version["id"],
        "versionNumber": version["number"],
        "title": version["title"],
        "summary": version.get("summary", ""),
        "document": version["document"],
        "revision": version["sourceRevision"],
        "workflowStatus": "published",
        "publicationStatus": "public",
        "publishedVersionId": version["id"],
        "publishedAt": case.get("publishedAt"),
        "createdAt": case.get("createdAt"),
        "updatedAt": version["createdAt"],
    }
