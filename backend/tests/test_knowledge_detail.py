from __future__ import annotations

from fastapi.testclient import TestClient

SOURCE = {
    "id": "ks-t1",
    "title": "《自然辩证法概论（2025版）》",
    "edition": "2025版",
    "summary": "教材全文已按章、节导入知识库",
    "chapterCount": 1,
    "sectionCount": 2,
    "status": "active",
}
CHAPTER = {"id": "kc-t1", "sourceId": "ks-t1", "index": 1, "title": "绪论"}
SECTION = {
    "id": "kn-t1-01",
    "sourceId": "ks-t1",
    "chapterId": "kc-t1",
    "chapter": "绪论",
    "index": 1,
    "unit": "第一单元",
    "title": "技术伦理",
    "summary": "章节摘要",
    "content": "生成式人工智能发展和管理机制。",
}


def _seed(client: TestClient) -> None:
    database = client.app.state.database
    database.knowledge_sources.insert_one(SOURCE)
    database.knowledge_chapters.insert_one(CHAPTER)
    database.knowledge_sections.insert_one(SECTION)


def test_source_detail_lists_chapters_without_section_content(client) -> None:
    _seed(client)
    response = client.get("/api/knowledge/ks-t1")
    assert response.status_code == 200
    assert response.json() == {
        "kind": "source",
        "id": "ks-t1",
        "title": SOURCE["title"],
        "edition": "2025版",
        "summary": SOURCE["summary"],
        "chapterCount": 1,
        "sectionCount": 2,
        "chapters": [{"id": "kc-t1", "title": "绪论", "index": 1}],
    }
    assert "content" not in response.json()


def test_section_detail_returns_readable_public_content(client) -> None:
    _seed(client)
    response = client.get("/api/knowledge/kn-t1-01")
    assert response.status_code == 200
    assert response.json() == {
        "kind": "section",
        "id": "kn-t1-01",
        "title": "技术伦理",
        "sourceTitle": SOURCE["title"],
        "chapter": "绪论",
        "unit": "第一单元",
        "index": 1,
        "summary": "章节摘要",
        "content": SECTION["content"],
    }


def test_unknown_knowledge_id_is_not_found(client) -> None:
    response = client.get("/api/knowledge/kn-missing")
    assert response.status_code == 404
    assert response.json() == {"detail": "知识条目不存在"}


def test_inactive_source_hides_its_detail_and_section_content(client) -> None:
    _seed(client)
    database = client.app.state.database
    database.knowledge_sources.update_one(
        {"id": SOURCE["id"]}, {"$set": {"status": "retired"}}
    )

    source_response = client.get("/api/knowledge/ks-t1")
    section_response = client.get("/api/knowledge/kn-t1-01")

    assert source_response.status_code == 404
    assert section_response.status_code == 404
    assert "content" not in section_response.text
