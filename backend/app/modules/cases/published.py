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
