from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.modules.cases.document_schema import citation_refs
from app.modules.documents import build_case_docx


def _citation(source_type: str = "material", source_id: str = "m-kcsz") -> dict:
    return {
        "type": "citation",
        "attrs": {"sourceType": source_type, "sourceId": source_id},
    }


def _text(value: str, marks: list[dict] | None = None) -> dict:
    node = {"type": "text", "text": value}
    if marks is not None:
        node["marks"] = marks
    return node


def _paragraph(*content: dict) -> dict:
    return {"type": "paragraph", "content": list(content)}


def _list_item(text: str) -> dict:
    return {"type": "listItem", "content": [_paragraph(_text(text))]}


def valid_document() -> dict:
    marks = [{"type": "bold"}, {"type": "italic"}, {"type": "strike"}]
    return {
        "type": "doc",
        "content": [
            {"type": "heading", "attrs": {"level": 3}, "content": [_text("标题")]},
            _paragraph(_text("正文", marks), {"type": "hardBreak"}, _text("换行")),
            {"type": "blockquote", "content": [_paragraph(_text("引用"))]},
            {"type": "bulletList", "content": [_list_item("项目")]},
            {
                "type": "orderedList",
                "attrs": {"start": 2},
                "content": [_list_item("编号")],
            },
        ],
    }


def _login_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def _create(client: TestClient, headers: dict[str, str], document: dict):
    return client.post(
        "/api/cases", headers=headers, json={"title": "Schema", "document": document}
    )


INVALID_DOCUMENTS = (
    ("unknown-node", {"type": "doc", "content": [{"type": "image"}]}),
    ("non-string-node", {"type": "doc", "content": [{"type": []}]}),
    (
        "unknown-mark",
        {"type": "doc", "content": [_paragraph(_text("x", [{"type": "underline"}]))]},
    ),
    (
        "non-string-mark",
        {"type": "doc", "content": [_paragraph(_text("x", [{"type": []}]))]},
    ),
    (
        "heading-level",
        {"type": "doc", "content": [{"type": "heading", "attrs": {"level": 4}}]},
    ),
    (
        "wrong-list-child",
        {"type": "doc", "content": [{"type": "bulletList", "content": [_paragraph()]}]},
    ),
    (
        "block-in-paragraph",
        {
            "type": "doc",
            "content": [_paragraph({"type": "heading", "attrs": {"level": 1}})],
        },
    ),
    (
        "empty-blockquote",
        {"type": "doc", "content": [{"type": "blockquote", "content": []}]},
    ),
    (
        "citation-extra-field",
        {
            "type": "doc",
            "content": [_paragraph(_text("x", [{**_citation(), "note": "多余"}]))],
        },
    ),
    (
        "citation-unknown-source-type",
        {
            "type": "doc",
            "content": [_paragraph(_text("x", [_citation("knowledge")]))],
        },
    ),
    (
        "citation-empty-source-id",
        {"type": "doc", "content": [_paragraph(_text("x", [_citation("case", "")]))]},
    ),
    (
        "text-with-content",
        {
            "type": "doc",
            "content": [_paragraph({"type": "text", "text": "x", "content": []})],
        },
    ),
    (
        "unknown-field",
        {"type": "doc", "content": [{"type": "paragraph", "mystery": True}]},
    ),
)


def test_current_tiptap_schema_is_accepted(client: TestClient) -> None:
    response = _create(client, _login_headers(client), valid_document())

    assert response.status_code == 200
    assert response.json()["document"] == valid_document()


def test_citation_mark_is_persisted(client: TestClient) -> None:
    document = {
        "type": "doc",
        "content": [_paragraph(_text("依据", [_citation()]))],
    }
    response = _create(client, _login_headers(client), document)

    assert response.status_code == 200
    assert response.json()["document"] == document


def test_citation_refs_keeps_first_occurrence_order() -> None:
    document = {
        "type": "doc",
        "content": [
            _paragraph(
                _text("甲", [_citation("case", "src-a")]),
                _text("乙", [_citation("material", "m-1"), {"type": "bold"}]),
                _text("丙", [_citation("case", "src-a")]),
            )
        ],
    }

    assert citation_refs(document) == [
        {"sourceType": "case", "sourceId": "src-a"},
        {"sourceType": "material", "sourceId": "m-1"},
    ]


def test_invalid_prosemirror_structure_returns_422(client: TestClient) -> None:
    headers = _login_headers(client)
    for name, document in INVALID_DOCUMENTS:
        response = _create(client, headers, document)
        assert response.status_code == 422, name
        errors = response.json()["detail"]
        assert any(error["loc"][-1] == "document" for error in errors), name


def test_prosemirror_resource_limits_return_422(client: TestClient) -> None:
    headers = _login_headers(client)
    too_large = {"type": "doc", "content": [_paragraph(_text("x" * 1_048_576))]}
    too_many = {"type": "doc", "content": [_paragraph() for _ in range(5_000)]}
    nested: dict = _paragraph()
    for _level in range(20):
        nested = {"type": "blockquote", "content": [nested]}

    for document in (too_large, too_many, {"type": "doc", "content": [nested]}):
        response = _create(client, headers, document)
        assert response.status_code == 422


def test_patch_uses_the_same_document_schema(client: TestClient) -> None:
    headers = _login_headers(client)
    current = client.get("/api/cases/c-draft-1").json()
    response = client.patch(
        "/api/cases/c-draft-1",
        headers=headers,
        json={
            "revision": current["revision"],
            "document": {"type": "doc", "content": [{"type": "unknown"}]},
        },
    )

    assert response.status_code == 422
    assert client.get("/api/cases/c-draft-1").json()["revision"] == current["revision"]


def test_docx_rejects_an_unknown_persisted_node() -> None:
    case = {
        "title": "非法真源",
        "document": {"type": "doc", "content": [{"type": "mystery"}]},
    }

    with pytest.raises(ValueError, match="未知节点"):
        build_case_docx(case, [])
