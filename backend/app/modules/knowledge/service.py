from __future__ import annotations

from pymongo.database import Database

from app.modules.cases.service import CaseError


def _chapter_rows(database: Database, source_id: str) -> list[dict]:
    rows = database.knowledge_chapters.find({"sourceId": source_id}).sort("index", 1)
    return [
        {"id": row["id"], "title": row["title"], "index": row["index"]} for row in rows
    ]


def _active_source(database: Database, source_id: str | None) -> dict | None:
    if not source_id:
        return None
    return database.knowledge_sources.find_one({"id": source_id, "status": "active"})


def source_view(database: Database, source: dict) -> dict:
    """教材级知识详情：结构信息与章节目录，不含正文。"""
    return {
        "kind": "source",
        "id": source["id"],
        "title": source["title"],
        "edition": source.get("edition"),
        "summary": source.get("summary"),
        "chapterCount": source.get("chapterCount"),
        "sectionCount": source.get("sectionCount"),
        "chapters": _chapter_rows(database, source["id"]),
    }


def section_view(database: Database, section: dict, source: dict) -> dict:
    """教材节知识详情：标题、出处与该节正文（公开可读）。"""
    return {
        "kind": "section",
        "id": section["id"],
        "title": section["title"],
        "sourceTitle": source.get("title") if source else None,
        "chapter": section.get("chapter"),
        "unit": section.get("unit"),
        "index": section.get("index"),
        "summary": section.get("summary"),
        "content": section.get("content"),
    }


def knowledge_detail(database: Database, knowledge_id: str) -> dict:
    """知识条目只读详情：教材结构公开可读，无权限级正文。"""
    source = _active_source(database, knowledge_id)
    if source:
        return source_view(database, source)
    section = database.knowledge_sections.find_one({"id": knowledge_id})
    source = _active_source(database, (section or {}).get("sourceId"))
    if section and source:
        return section_view(database, section, source)
    raise CaseError(404, "知识条目不存在")
