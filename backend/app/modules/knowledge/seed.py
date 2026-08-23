from __future__ import annotations

import re
from pathlib import Path

from pymongo.database import Database

BOOK_PATH = (
    Path(__file__).resolve().parents[4] / "files" / "seed" / "book" / "zrbjf-2025.md"
)
SOURCE_ID = "ks-zr"
SOURCE_TITLE = "《自然辩证法概论（2025版）》"


def _heading(line: str) -> tuple[int, str] | None:
    match = re.match(r"^(#{1,3})\s+(.+)$", line)
    return (len(match[1]), match[2].strip()) if match else None


def _summary(content: str) -> str:
    return " ".join(content.split())[:180]


def _flush_section(state: dict) -> None:
    section = state.pop("section", None)
    if not section:
        return
    content = "\n".join(section.pop("lines")).strip()
    state["sections"].append(
        {**section, "summary": _summary(content), "content": content}
    )


def _start_chapter(state: dict, title: str) -> None:
    index = len(state["chapters"]) + 1
    chapter = {
        "id": f"kc-{index:02}",
        "sourceId": SOURCE_ID,
        "index": index,
        "title": title,
    }
    state.update(chapter=chapter, unit=None, section_index=0)
    state["chapters"].append(chapter)


def _start_section(state: dict, title: str) -> None:
    state["section_index"] += 1
    chapter = state["chapter"]
    state["section"] = {
        "id": f"kn-{chapter['index']:02}-{state['section_index']:02}",
        "sourceId": SOURCE_ID,
        "chapterId": chapter["id"],
        "chapter": chapter["title"],
        "index": state["section_index"],
        "title": title,
        "unit": state.get("unit"),
        "lines": [],
    }


def _apply_heading(state: dict, level: int, title: str) -> None:
    _flush_section(state)
    if level == 1:
        _start_chapter(state, title)
    elif level == 2:
        state["unit"] = title
    elif state.get("chapter"):
        _start_section(state, title)


def parse_book(text: str) -> tuple[list[dict], list[dict]]:
    state = {"chapters": [], "sections": []}
    for line in text.splitlines():
        heading = _heading(line)
        if heading:
            _apply_heading(state, *heading)
        elif state.get("section") is not None:
            state["section"]["lines"].append(line)
    _flush_section(state)
    return state["chapters"], state["sections"]


def _source(chapters: list[dict], sections: list[dict]) -> dict:
    return {
        "id": SOURCE_ID,
        "title": SOURCE_TITLE,
        "edition": "2025版",
        "summary": "教材全文已按章、节导入知识库，可用于平台检索与教学案例编写。",
        "chapterCount": len(chapters),
        "sectionCount": len(sections),
        "status": "active",
    }


def _replace_rows(collection, source_id: str, rows: list[dict]) -> None:
    ids = [row["id"] for row in rows]
    collection.delete_many({"sourceId": source_id, "id": {"$nin": ids}})
    for row in rows:
        collection.replace_one({"id": row["id"]}, row, upsert=True)


def seed_knowledge(database: Database) -> None:
    chapters, sections = parse_book(BOOK_PATH.read_text(encoding="utf-8"))
    database.knowledge_sources.replace_one(
        {"id": SOURCE_ID}, _source(chapters, sections), upsert=True
    )
    _replace_rows(database.knowledge_chapters, SOURCE_ID, chapters)
    _replace_rows(database.knowledge_sections, SOURCE_ID, sections)
