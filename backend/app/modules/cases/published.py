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
        version = self.database.case_versions.find_one(
            {"id": case.get("publishedVersionId"), "caseId": case["id"]}
        )
        if not version or case.get("publicationStatus") != "public":
            raise CaseError(404, "案例不存在")
        return _published_view(case, version)

    def read_public_version(self, case: dict, version_id: str) -> dict:
        """公共阅读固定版本：即使 admin/owner 也按读者权限判定。"""
        version = self.database.case_versions.find_one(
            {"id": version_id, "caseId": case["id"]}
        )
        if not version_readable(self.database, case, version_id, version, False):
            raise CaseError(404, "案例版本不存在")
        return _published_view(case, version)


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


def _published_view(case: dict, version: dict) -> dict:
    metadata = {
        field: version["metadata"].get(field) for field in PUBLIC_METADATA_FIELDS
    }
    return {
        **metadata,
        "id": case["id"],
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
