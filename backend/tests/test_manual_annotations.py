from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient


HEADING = "一、教学说明"


def login(client: TestClient, username: str, password: str) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()


def document(*paragraphs: str) -> dict:
    nodes = [{"type": "heading", "attrs": {"level": 1}, "content": [{"type": "text", "text": HEADING}]}]
    nodes.extend({"type": "paragraph", "content": [{"type": "text", "text": text}]} for text in paragraphs)
    return {"type": "doc", "content": nodes}


def create_case(client: TestClient, user: dict, *paragraphs: str) -> dict:
    response = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": user["csrfToken"]},
        json={"title": "手动批注测试", "document": document(*paragraphs)},
    )
    assert response.status_code == 200
    return response.json()


def selection(text: str, prior_paragraphs: tuple[str, ...] = (), revision: int = 1) -> dict:
    offset = len(HEADING) + 3
    for prior in prior_paragraphs:
        offset += len(prior) + 2
    return {
        "from": offset,
        "to": offset + len(text),
        "quote": text,
        "section": HEADING,
        "quoteHash": hashlib.sha256(text.encode()).hexdigest(),
        "revision": revision,
    }


def annotation_payload(
    text: str, prior_paragraphs: tuple[str, ...] = (), revision: int = 1,
    content: str = "请补充教学依据。",
) -> dict:
    return {
        **selection(text, prior_paragraphs, revision),
        "content": content,
        "source": "manual",
    }


def annotation_path(case_id: str, annotation_id: str = "") -> str:
    root = f"/api/cases/{case_id}/annotations"
    return f"{root}/{annotation_id}" if annotation_id else root


def post_annotation(client: TestClient, user: dict, case: dict, payload: dict):
    return client.post(
        annotation_path(case["id"]),
        headers={"X-CSRF-Token": user["csrfToken"]},
        json=payload,
    )


def create_manual(client: TestClient, user: dict, case: dict, text: str) -> dict:
    response = post_annotation(client, user, case, annotation_payload(text))
    assert response.status_code == 201
    return response.json()


def assert_anchor(annotation: dict, user: dict, case: dict, text: str) -> None:
    assert annotation["createdBy"] == user["user"]["id"]
    assert annotation["revision"] == case["revision"]
    assert annotation["from"] < annotation["to"]
    assert annotation["quoteHash"] == hashlib.sha256(text.encode()).hexdigest()
    assert annotation["status"] == "pending"


def edit_annotation(client: TestClient, user: dict, case: dict, annotation: dict):
    return client.patch(
        annotation_path(case["id"], annotation["id"]),
        headers={"X-CSRF-Token": user["csrfToken"]},
        json={"content": "请补充课程目标对应关系。"},
    )


def cross_block_payload(texts: tuple[str, str]) -> dict:
    payload = selection("".join(texts))
    payload["from"] = selection(texts[0])["from"]
    payload["to"] = payload["from"] + len(texts[0]) + 2
    return {**payload, "content": "不能跨段。", "source": "manual"}


def save_title(client: TestClient, user: dict, case: dict) -> None:
    response = client.patch(
        f"/api/cases/{case['id']}",
        headers={"X-CSRF-Token": user["csrfToken"]},
        json={"revision": case["revision"], "title": "修订后的标题"},
    )
    assert response.status_code == 200


def test_author_can_crud_manual_annotation_with_anchor_fields(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "供应中断周期不明")
    annotation = create_manual(client, user, case, "供应中断周期不明")
    assert_anchor(annotation, user, case, "供应中断周期不明")
    edited = edit_annotation(client, user, case, annotation)
    assert edited.status_code == 200
    assert edited.json()["content"] == "请补充课程目标对应关系。"
    removed = client.delete(
        annotation_path(case["id"], annotation["id"]),
        headers={"X-CSRF-Token": user["csrfToken"]},
    )
    assert removed.status_code == 204
    assert client.get(annotation_path(case["id"])).json() == []


def test_manual_annotation_rejects_stale_or_cross_block_anchor(client: TestClient) -> None:
    user = login(client, "user", "user123")
    texts = ("第一段正文", "第二段正文")
    case = create_case(client, user, *texts)
    response = post_annotation(client, user, case, cross_block_payload(texts))
    assert response.status_code == 409
    assert "同一正文段落" in response.json()["detail"]
    save_title(client, user, case)
    stale = post_annotation(client, user, case, annotation_payload(texts[0]))
    assert stale.status_code == 409
    assert client.get(annotation_path(case["id"])).json() == []


def test_manual_annotation_permissions_leave_no_ghost_row(client: TestClient) -> None:
    owner = login(client, "user", "user123")
    case = create_case(client, owner, "仅作者可以批注")
    admin = login(client, "admin", "admin123")
    denied = post_annotation(client, admin, case, annotation_payload("仅作者可以批注"))
    assert denied.status_code == 403
    assert client.get(annotation_path(case["id"])).json() == []

    owner = login(client, "user", "user123")
    created = create_manual(client, owner, case, "仅作者可以批注")
    admin = login(client, "admin", "admin123")
    edited = client.patch(
        annotation_path(case["id"], created["id"]),
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={"content": "越权修改"},
    )
    assert edited.status_code == 403
