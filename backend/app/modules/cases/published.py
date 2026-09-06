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
        version = self._published_version(case)
        if not version or case.get("publicationStatus") != "public":
            raise CaseError(404, "案例不存在")
        return published_view(case, version)

    def _published_version(self, case: dict) -> dict | None:
        return self._find_version(case.get("publishedVersionId"), case["id"])

    def read_version(self, case: dict, version_id: str, user: dict | None) -> dict:
        version = self._find_version(version_id, case["id"])
        internal = bool(
            user
            and (user["role"] == "admin" or case["ownerId"] == user["id"])
        )
        if not version or not self._version_readable(case, version, internal):
            raise CaseError(404, "案例版本不存在")
        return _version_view(case, version)

    def read_public_version(
        self, case: dict, version_id: str, user: dict | None
    ) -> dict:
        version = self._find_version(version_id, case["id"])
        internal = bool(
            user
            and (user["role"] == "admin" or case["ownerId"] == user["id"])
        )
        if not version or not self._version_readable(case, version, internal):
            raise CaseError(404, "案例版本不存在")
        view = published_view(case, version)
        view["versionId"] = version["id"]
        view["versionNumber"] = version["number"]
        return view

    def _find_version(self, version_id: str, case_id: str) -> dict | None:
        return self.database.case_versions.find_one(
            {"id": version_id, "caseId": case_id}
        )

    def _version_readable(self, case: dict, version: dict, internal: bool) -> bool:
        return version_readable(
            self.database, case, version["id"], version, internal
        )


def version_readable(
    database: Database,
    case: dict,
    version_id: str,
    version: dict | None,
    internal: bool,
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
    )
    return bool(approved)


def published_view(case: dict, version: dict) -> dict:
    metadata = {
        field: version["metadata"].get(field) for field in PUBLIC_METADATA_FIELDS
    }
    return {
        **metadata,
        "id": case["id"],
        "versionId": version["id"],
        "versionNumber": version["number"],
        "title": version["title"],
        "summary": version.get("summary", ""),
        "tagIds": version["metadata"].get("tagIds", []),
        "document": version["document"],
        "revision": version["sourceRevision"],
        "workflowStatus": "published",
        "publicationStatus": "public",
        "publishedVersionId": version["id"],
        "publishedAt": case.get("publishedAt"),
        "createdAt": case.get("createdAt"),
        "updatedAt": version["createdAt"],
    }


def _version_view(case: dict, version: dict) -> dict:
    metadata = {
        field: version["metadata"].get(field) for field in PUBLIC_METADATA_FIELDS
    }
    return {
        **metadata,
        "id": case["id"],
        "versionId": version["id"],
        "versionNumber": version["number"],
        "title": version["title"],
        "summary": version.get("summary", ""),
        "document": version["document"],
        "publishedAt": case.get("publishedAt"),
        "createdAt": version["createdAt"],
    }
