from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.modules.search.client import create_reader, index_epoch, wait_task
from app.modules.search.indexer import catalog_settings
from app.modules.search.meilisearch import (
    CatalogKey,
    CatalogRequest,
    MeilisearchCatalog,
    Principal,
    SearchUnavailable,
)
from app.modules.search.projection import project_catalog_documents

pytestmark = pytest.mark.e2e("MEILI_CONTRACT_URL", "MEILI_CONTRACT_KEY_FILE")


def _material(index: int) -> dict:
    levels = ("public", "campus", "private")
    return {
        "id": "shared-id" if index == 0 else f"m-{index:05}",
        "title": f"科学家精神思政素材 {index:05}",
        "summary": f"不可泄露的素材摘要 {index:05}",
        "sourceUrl": f"https://secret.invalid/{index}",
        "tags": ["科学家精神" if index % 2 == 0 else "思政课堂"],
        "publishedAt": (date(2026, 8, 13) - timedelta(days=index)).isoformat(),
        "materialType": "文档" if index % 2 == 0 else "视频",
        "authority": "original" if index % 2 == 0 else "secondary",
        "accessLevel": levels[index % 3],
        "status": "active",
        "createdBy": "u-owner",
        "publicReferenceCount": 1,
    }


def _materials() -> list[dict]:
    rows = []
    for index in range(12_480):
        rows.extend(project_catalog_documents("material", _material(index)))
    return rows


def _case(case_id: str, title: str) -> dict:
    version = {
        "caseId": case_id,
        "title": title,
        "summary": "依托场馆实践与专业课程建设思政课堂",
        "document": {"type": "doc", "content": []},
        "attachments": [],
        "metadata": {"theoryPoints": ["科学家精神"]},
    }
    publication = {"publishedAt": "2026-08-14", "ownerId": "u-owner"}
    return project_catalog_documents("case", version, publication)[0]


def _knowledge() -> list[dict]:
    source = {"id": "source-1", "title": "自然辩证法", "status": "active"}
    section = {
        "id": "section-1",
        "sourceId": "source-1",
        "chapterId": "chapter-1",
        "chapter": "科技伦理",
        "index": 1,
        "title": "生成式人工智能治理",
        "content": "生成式人工智能的发展与管理机制",
    }
    return [
        *project_catalog_documents("knowledge_source", source),
        *project_catalog_documents("knowledge_section", section),
    ]


def _documents() -> list[dict]:
    cases = [
        _case("spirit-case", "如何将科学家精神融入思政课堂"),
        _case("shared-id", "同名案例实体"),
    ]
    meta = {
        "catalogId": "catalog-meta",
        "docClass": "catalog-meta",
        "generation": "contract-generation",
    }
    return [meta, *_materials(), *cases, *_knowledge()]


def _load(client, uid: str) -> None:
    wait_task(client, client.create_index(uid, {"primaryKey": "catalogId"}))
    index = client.index(uid)
    wait_task(client, index.update_settings(catalog_settings()))
    rows = _documents()
    for start in range(0, len(rows), 500):
        wait_task(client, index.add_documents(rows[start : start + 500]))


def _meili_client():
    import meilisearch

    key_file = os.environ["MEILI_CONTRACT_KEY_FILE"]
    key = Path(key_file).read_text(encoding="utf-8").strip()
    client = meilisearch.Client(os.environ["MEILI_CONTRACT_URL"], key)
    return client, key_file


@pytest.fixture(scope="module")
def catalog():
    client, key_file = _meili_client()
    url = os.environ["MEILI_CONTRACT_URL"]
    uid = f"catalog_contract_{uuid.uuid4().hex}"
    _load(client, uid)

    try:
        yield (
            MeilisearchCatalog(create_reader(url, key_file)),
            uid,
            index_epoch(client, uid),
        )
    finally:
        wait_task(client, client.delete_index(uid))


def _request(uid: str, epoch: str, **changes) -> CatalogRequest:
    values = {
        "q": "",
        "kind": "material",
        "generation": "contract-generation",
        "index_uid": uid,
        "index_epoch": epoch,
        "page_size": 100,
        "offset": 0,
        "filters": {},
        "principal": Principal(None, "anonymous"),
    }
    return CatalogRequest(**{**values, **changes})


def _walk_material_ids(catalog, uid: str, epoch: str) -> list[str]:
    ids, offset = [], 0
    while True:
        page = catalog.search(
            _request(uid, epoch, offset=offset, include_metadata=offset == 0)
        )
        ids.extend(item["id"] for item in page.items)
        if not page.has_next:
            return ids
        offset += 100


def _redacted_material() -> dict:
    return {
        "id": "m-00001",
        "kind": "material",
        "title": "科学家精神思政素材 00001",
        "accessLevel": "campus",
        "contentAvailable": False,
        "hasFile": False,
        "score": 1,
    }


def _level_counts(page) -> dict[str, int]:
    return {row["value"]: row["count"] for row in page.metadata.facets["accessLevel"]}


def test_real_catalog_walks_12480_acl_results_in_global_date_order(catalog) -> None:
    catalog, uid, epoch = catalog
    ids = _walk_material_ids(catalog, uid, epoch)
    assert (len(ids), len(set(ids))) == (12_480, 12_480)
    assert ids[:3] == ["shared-id", "m-00001", "m-00002"]


def test_real_catalog_redacts_denied_material_and_self_excludes_facets(catalog) -> None:
    catalog, uid, epoch = catalog
    page = catalog.search(_request(uid, epoch, page_size=3))
    assert page.items[0]["contentAvailable"] is True
    assert page.items[1] == _redacted_material()
    filtered = catalog.search(
        _request(uid, epoch, filters={"accessLevel": ("public",)})
    )
    assert filtered.metadata.total == 4_160
    assert _level_counts(filtered) == {
        "public": 4_160,
        "campus": 4_160,
        "private": 4_160,
    }


def test_real_catalog_handles_natural_questions_and_knowledge_levels(catalog) -> None:
    catalog, uid, epoch = catalog
    question = catalog.search(
        _request(uid, epoch, q="如何将科学家精神融入思政课堂", kind="all", page_size=20)
    )
    assert "spirit-case" in {item["id"] for item in question.items}
    sources = catalog.search(_request(uid, epoch, kind="knowledge", page_size=20))
    sections = catalog.search(
        _request(uid, epoch, q="生成式人工智能", kind="knowledge", page_size=20)
    )
    assert [item["id"] for item in sources.items] == ["source-1"]
    assert [item["id"] for item in sections.items] == ["section-1"]


def test_real_catalog_revocation_does_not_cross_catalog_kinds(catalog) -> None:
    catalog, uid, epoch = catalog
    page = catalog.search(
        _request(
            uid,
            epoch,
            kind="all",
            page_size=20,
            excluded_keys=(CatalogKey("case", "shared-id"),),
        )
    )
    matching = [item for item in page.items if item["id"] == "shared-id"]
    assert [item["kind"] for item in matching] == ["material"]


def test_real_catalog_rejects_an_unconfirmed_index_epoch(catalog) -> None:
    catalog, uid, _epoch = catalog

    with pytest.raises(SearchUnavailable, match="同步"):
        catalog.search(_request(uid, "unconfirmed-epoch"))
