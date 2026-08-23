from __future__ import annotations

from app.modules.search.projection import project_catalog_documents

CASE_VERSION = {
    "caseId": "c-01",
    "title": "科学报国",
    "summary": "案例摘要",
    "document": {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "正文白鹭词"}],
            }
        ],
    },
    "attachments": [
        {
            "name": "公开附件雪松.txt",
            "accessLevel": "public",
            "searchText": "公开雪松内容",
        },
        {
            "name": "校内附件山茶.txt",
            "accessLevel": "campus",
            "searchText": "校内山茶内容",
        },
        {
            "name": "私密附件海棠.txt",
            "accessLevel": "private",
            "searchText": "私密海棠内容",
        },
    ],
    "metadata": {
        "typeId": "ct-person",
        "typeName": "人物传记类",
        "course": "中国近现代史纲要",
        "author": "案例组",
        "organization": "上海大学",
        "stageText": "本科生",
        "audience": "ug",
        "purpose": "课堂教学",
        "likes": 7,
        "theoryPoints": ["科学家精神"],
    },
}
CASE_PUBLICATION = {
    "publishedAt": "2026-08-13T08:00:00+00:00",
    "ownerId": "u-owner",
}
CASE_DOCUMENT = {
    "id": "c-01",
    "kind": "case",
    "title": "科学报国",
    "summary": "案例摘要",
    "publishedAt": CASE_PUBLICATION["publishedAt"],
    "typeName": "人物传记类",
    "typeId": "ct-person",
    "course": "中国近现代史纲要",
    "author": "案例组",
    "organization": "上海大学",
    "stageText": "本科生",
    "audience": "ug",
    "purpose": "课堂教学",
    "likes": 7,
    "theoryPoints": ["科学家精神"],
    "tags": ["科学家精神"],
    "createdBy": "u-owner",
}
KNOWLEDGE_SOURCE = {
    "id": "ks-01",
    "title": "《自然辩证法概论》",
    "edition": "2025版",
    "summary": "教材摘要",
    "chapterCount": 7,
    "sectionCount": 52,
}
SOURCE_DOCUMENT = {
    "catalogId": "knowledge-source-ks-01",
    "id": "ks-01",
    "kind": "knowledge",
    "docClass": "knowledge-source",
    "knowledgeLevel": "source",
    "title": "《自然辩证法概论》",
    "edition": "2025版",
    "summary": "教材摘要",
    "chapterCount": 7,
    "sectionCount": 52,
    "searchableText": "《自然辩证法概论》 教材摘要 2025版",
}
KNOWLEDGE_SECTION = {
    "id": "kn-01-02",
    "sourceId": "ks-01",
    "chapterId": "kc-01",
    "chapter": "绪论",
    "index": 2,
    "unit": "第一单元",
    "title": "技术伦理",
    "summary": "章节摘要",
    "content": "生成式人工智能发展和管理机制",
}
SECTION_DOCUMENT = {
    "catalogId": "knowledge-section-kn-01-02",
    "id": "kn-01-02",
    "kind": "knowledge",
    "docClass": "knowledge-section",
    "knowledgeLevel": "section",
    "sourceId": "ks-01",
    "chapterId": "kc-01",
    "chapter": "绪论",
    "index": 2,
    "unit": "第一单元",
    "title": "技术伦理",
    "summary": "章节摘要",
    "searchableText": "技术伦理 章节摘要 绪论 第一单元 生成式人工智能发展和管理机制",
}
MATERIAL = {
    "id": "m-01",
    "title": "公开名称",
    "summary": "受限摘要",
    "excerpt": "受限正文",
    "source": "来源单位",
    "sourceUrl": "https://example.invalid/material",
    "tags": ["科学家精神"],
    "publishedAt": "2026-08-13",
    "materialType": "政策文件",
    "authority": "original",
    "accessLevel": "private",
    "status": "active",
    "createdBy": "u-owner",
    "publicReferenceCount": 2,
    "citedCount": 9,
    "filename": "原文.pdf",
    "mediaType": "application/pdf",
    "size": 2048,
    "blobId": "digest",
}
MATERIAL_DOCUMENT = {
    "catalogId": "material-m-01-full",
    "id": "m-01",
    "kind": "material",
    "docClass": "material-full",
    "title": "公开名称",
    "summary": "受限摘要",
    "excerpt": "受限正文",
    "source": "来源单位",
    "sourceUrl": "https://example.invalid/material",
    "tags": ["科学家精神"],
    "publishedAt": "2026-08-13",
    "materialType": "政策文件",
    "authority": "original",
    "accessLevel": "private",
    "status": "active",
    "createdBy": "u-owner",
    "publicReferenceCount": 2,
    "citedCount": 9,
    "filename": "原文.pdf",
    "mediaType": "application/pdf",
    "size": 2048,
    "hasFile": True,
    "searchableText": "公开名称 受限摘要 受限正文 来源单位 科学家精神",
}


def test_published_case_version_projects_searchable_catalog_document() -> None:
    documents = project_catalog_documents("case", CASE_VERSION, CASE_PUBLICATION)
    assert [(row["catalogId"], row["docClass"]) for row in documents] == [
        ("case-c-01-public", "case-public"),
        ("case-c-01-campus", "case-campus"),
        ("case-c-01-private", "case-private"),
    ]
    assert all(
        {key: row[key] for key in CASE_DOCUMENT} == CASE_DOCUMENT for row in documents
    )


def test_case_projection_keeps_attachment_content_in_its_acl_layer() -> None:
    public, campus, private = project_catalog_documents(
        "case",
        CASE_VERSION,
        CASE_PUBLICATION,
    )
    assert "正文白鹭词" in public["searchableText"]
    assert all(
        row["searchableText"].count("附件") == 3 for row in (public, campus, private)
    )
    assert "公开雪松内容" in public["searchableText"]
    assert "校内山茶内容" not in public["searchableText"]
    assert "校内山茶内容" in campus["searchableText"]
    assert "私密海棠内容" not in campus["searchableText"]
    assert "私密海棠内容" in private["searchableText"]


def test_knowledge_source_and_section_share_catalog_kind() -> None:
    [source] = project_catalog_documents("knowledge_source", KNOWLEDGE_SOURCE)
    [section] = project_catalog_documents("knowledge_section", KNOWLEDGE_SECTION)
    assert source == SOURCE_DOCUMENT
    assert section == SECTION_DOCUMENT


def test_material_projection_keeps_acl_and_title_only_search_fields_separate() -> None:
    full, restricted = project_catalog_documents("material", MATERIAL)
    assert full == MATERIAL_DOCUMENT
    assert restricted == {
        "catalogId": "material-m-01-restricted",
        "id": "m-01",
        "kind": "material",
        "docClass": "material-restricted",
        "title": "公开名称",
        "publishedAt": "2026-08-13",
        "accessLevel": "private",
        "createdBy": "u-owner",
        "publicReferenceCount": 2,
        "hasFile": True,
        "workingCaseIds": None,
        "publishedVersionIds": None,
        "searchableText": "公开名称",
    }


def test_material_projection_accepts_optional_search_fields() -> None:
    document, _restricted = project_catalog_documents(
        "material",
        {
            "id": "m-minimal",
            "title": "最小素材",
            "accessLevel": "public",
            "status": "active",
            "createdBy": "u-owner",
            "publicReferenceCount": 0,
        },
    )
    assert document["catalogId"] == "material-m-minimal-full"
    assert document["searchableText"] == "最小素材"
    assert document["hasFile"] is False
