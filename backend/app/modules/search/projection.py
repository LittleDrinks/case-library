from __future__ import annotations

CASE_FIELDS = (
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
)
SOURCE_FIELDS = ("edition", "summary", "chapterCount", "sectionCount")
SECTION_FIELDS = (
    "sourceId",
    "chapterId",
    "chapter",
    "index",
    "unit",
    "summary",
)
MATERIAL_FIELDS = (
    "summary",
    "excerpt",
    "source",
    "sourceUrl",
    "tags",
    "publishedAt",
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
)
CASE_LEVELS = ("public", "campus", "private")


def _text(*values) -> str:
    parts = []
    for value in values:
        parts.extend(value if isinstance(value, list) else [value])
    return " ".join(str(value).strip() for value in parts if value)


def _document_text(document: dict) -> str:
    values, stack = [], [document]
    while stack:
        node = stack.pop()
        if node.get("type") == "text":
            values.append(node["text"])
        stack.extend(reversed(node.get("content", [])))
    return _text(values)


def _case_fields(version: dict, publication: dict) -> dict:
    metadata = version.get("metadata", {})
    return {
        "id": version["caseId"],
        "kind": "case",
        "title": version["title"],
        "summary": version.get("summary", ""),
        "publishedAt": publication.get("publishedAt", ""),
        **{field: metadata.get(field) for field in CASE_FIELDS},
        "tags": metadata.get("theoryPoints", []),
        "createdBy": publication["ownerId"],
    }


def _attachment_names(version: dict) -> str:
    return _text([attachment["name"] for attachment in version["attachments"]])


def _attachment_text(version: dict, level: str) -> str:
    allowed = CASE_LEVELS[: CASE_LEVELS.index(level) + 1]
    return _text(
        [
            attachment["searchText"]
            for attachment in version["attachments"]
            if attachment["accessLevel"] in allowed
        ]
    )


def _case_searchable(fields: dict, version: dict) -> str:
    return _text(
        fields["title"],
        fields["summary"],
        fields["course"],
        fields["author"],
        fields["tags"],
        _document_text(version["document"]),
        _attachment_names(version),
    )


def case_catalog_ids(case_id: str) -> list[str]:
    return [f"case-{case_id}-{level}" for level in CASE_LEVELS]


def _case_documents(version: dict, publication: dict) -> list[dict]:
    fields = _case_fields(version, publication)
    base = _case_searchable(fields, version)
    return [
        {
            **fields,
            "catalogId": catalog_id,
            "docClass": f"case-{level}",
            "searchableText": _text(base, _attachment_text(version, level)),
        }
        for level, catalog_id in zip(
            CASE_LEVELS, case_catalog_ids(version["caseId"]), strict=True
        )
    ]


def _knowledge_document(record: dict, level: str) -> dict:
    fields = SOURCE_FIELDS if level == "source" else SECTION_FIELDS
    document = {
        "catalogId": f"knowledge-{level}-{record['id']}",
        "id": record["id"],
        "kind": "knowledge",
        "docClass": f"knowledge-{level}",
        "knowledgeLevel": level,
        "title": record["title"],
        **{field: record.get(field) for field in fields},
    }
    content = record.get("content") if level == "section" else record.get("edition")
    document["searchableText"] = _text(
        document["title"],
        document.get("summary"),
        document.get("chapter"),
        document.get("unit"),
        content,
    )
    return document


def _material_document(record: dict) -> dict:
    document = {
        "catalogId": f"material-{record['id']}-full",
        "id": record["id"],
        "kind": "material",
        "docClass": "material-full",
        "title": record["title"],
        **{field: record.get(field) for field in MATERIAL_FIELDS},
        "hasFile": bool(record.get("blobId")),
    }
    document["searchableText"] = _text(
        document["title"],
        document.get("summary"),
        document.get("excerpt"),
        document.get("source"),
        document.get("tags"),
    )
    return document


def _restricted_material(document: dict) -> dict:
    fields = (
        "id",
        "kind",
        "title",
        "publishedAt",
        "accessLevel",
        "createdBy",
        "publicReferenceCount",
        "hasFile",
        "workingCaseIds",
        "publishedVersionIds",
    )
    return {
        "catalogId": f"material-{document['id']}-restricted",
        "docClass": "material-restricted",
        "searchableText": document["title"],
        **{field: document.get(field) for field in fields},
    }


def _material_documents(record: dict, context: dict) -> list[dict]:
    full = {**_material_document(record), **context}
    return [full, _restricted_material(full)]


def project_catalog_documents(
    kind: str,
    record: dict,
    context: dict | None = None,
) -> list[dict]:
    if kind == "case":
        return _case_documents(record, context or {})
    if kind in {"knowledge_source", "knowledge_section"}:
        return [_knowledge_document(record, kind.removeprefix("knowledge_"))]
    if kind == "material":
        return _material_documents(record, context or {})
    raise ValueError(f"unsupported catalog kind: {kind}")
