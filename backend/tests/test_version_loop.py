"""小颗粒度历史版本闭环（Issue #293）：手动版本、恢复保留批注、AI 候选独立成稿。"""

from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from app.modules.agent import prosemirror


def login(client: TestClient, username: str = "user", password: str = "user123"):
    return client.post("/api/auth/login", json={"username": username, "password": password})

HEADING = "一、教学说明"


def heading_document(text: str) -> dict:
    """带 h1 小节标题的正文：批注锚定依赖 section 标题计算。"""
    return {
        "type": "doc",
        "content": [
            {"type": "heading", "attrs": {"level": 1}, "content": [{"type": "text", "text": HEADING}]},
            {"type": "paragraph", "content": [{"type": "text", "text": text}]},
        ],
    }


def paragraph_document(text: str) -> dict:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def document_update(case: dict, document: dict) -> dict:
    _updated, steps = prosemirror.replace_document(case["document"], document)
    return {"document": document, "steps": steps, "revision": case["revision"]}


def _save_content(client, auth: dict, case: dict, text: str) -> dict:
    response = client.patch(
        f"/api/cases/{case['id']}",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={**document_update(case, heading_document(text))},
    )
    assert response.status_code == 200
    return response.json()


def _lifecycle(client, auth: dict, case: dict, command: str, **extra):
    return client.post(
        f"/api/cases/{case['id']}/lifecycle",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"command": command, "revision": case["revision"], **extra},
    )


def _history(client, case_id: str) -> dict:
    return client.get(f"/api/cases/{case_id}/history").json()


def _frozen_version(client, auth: dict, marker: str):
    """创建案例、投稿、撤回；返回（工作稿，投稿版本）供恢复实验。"""
    created = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": marker, "document": heading_document(f"{marker} 冻结正文")},
    ).json()
    submitted = _lifecycle(client, auth, created, "submit").json()
    reopened = _lifecycle(client, auth, submitted["case"], "withdraw").json()
    return reopened["case"], submitted["version"]


def _draft_annotation(client, auth: dict, case: dict, quote: str, note: str) -> dict:
    """quote 需为正文段落 utf16 切片；h1 后段落 block 内 start<pos<=end。"""
    response = client.post(
        f"/api/cases/{case['id']}/annotations",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={
            "quote": quote, "section": HEADING, "content": note, "source": "manual",
            "revision": case["revision"],
            "from": 10, "to": 10 + len(quote.encode("utf-16-le")) // 2,
            "quoteHash": hashlib.sha256(quote.encode()).hexdigest(),
        },
    )
    assert response.status_code == 201, response.json()
    return response.json()


def _version_annotation(client, auth: dict, case: dict) -> dict:
    """再投稿→管理员开审挂版本批注→作者撤回；返回（工作稿，被批注版本，批注）。"""
    submitted = _lifecycle(client, auth, case, "submit").json()
    admin = login(client, "admin", "admin123").json()
    started = _lifecycle(client, admin, submitted["case"], "start").json()
    response = client.post(
        f"/api/cases/{case['id']}/annotations",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={
            "quote": HEADING, "section": HEADING,
            "content": "历史版本批注", "source": "admin",
        },
    )
    assert response.status_code == 201, response.json()
    note = response.json()
    assert note["versionId"] == submitted["version"]["id"]
    owner = login(client).json()
    reopened = _lifecycle(client, owner, started["case"], "withdraw").json()
    return reopened["case"], submitted["version"], note


def test_author_creates_named_manual_version(client: TestClient) -> None:
    auth = login(client).json()
    case = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "手动版本案例", "document": paragraph_document("手动正文")},
    ).json()
    saved = _save_content(client, auth, case, "手动正文 第二版")
    created = client.post(
        f"/api/cases/{case['id']}/versions",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "补充教学目标", "revision": saved["revision"]},
    )
    assert created.status_code == 200
    version = created.json()
    assert version["kind"] == "manual"
    assert version["title"] == "补充教学目标"
    assert version["number"] == 1
    rows = _history(client, case["id"])["versions"]
    assert [row["kind"] for row in rows] == ["manual"]
    assert rows[0]["document"] == saved["document"]
    refresh = client.get(f"/api/cases/{case['id']}").json()
    assert refresh["revision"] == saved["revision"] + 1
    stale = client.post(
        f"/api/cases/{case['id']}/versions",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "旧页签", "revision": saved["revision"]},
    )
    assert stale.status_code == 409


def test_manual_version_requires_owner_and_draft(client: TestClient) -> None:
    auth = login(client).json()
    case = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "权限案例", "document": paragraph_document("权限正文")},
    ).json()
    admin = login(client, "admin", "admin123").json()
    stranger = client.post(
        f"/api/cases/{case['id']}/versions",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={"title": "管理员代建", "revision": case["revision"]},
    )
    assert stranger.status_code == 403

    owner = login(client).json()
    submitted = _lifecycle(client, owner, case, "submit").json()
    frozen = client.post(
        f"/api/cases/{case['id']}/versions",
        headers={"X-CSRF-Token": owner["csrfToken"]},
        json={"title": "冻结中创建", "revision": submitted["case"]["revision"]},
    )
    assert frozen.status_code == 409


def test_restore_keeps_current_work_and_appends_restore_record(client: TestClient) -> None:
    auth = login(client).json()
    case, version = _frozen_version(client, auth, "恢复闭环")
    changed = _save_content(client, auth, case, "恢复前未保存的正文")
    draft_note = _draft_annotation(
        client, auth, changed, "复前未保存的正文", "恢复前草稿批注",
    )
    changed, annotated_version, version_note = _version_annotation(client, auth, changed)

    author = login(client).json()
    restored = _lifecycle(
        client, author, changed, "overwrite", targetId=annotated_version["id"],
    )
    assert restored.status_code == 200

    rows = _history(client, case["id"])["versions"]
    kinds = [row["kind"] for row in rows]
    assert kinds == ["submission", "submission", "manual", "restore"]
    baseline = rows[2]
    assert baseline["title"] == "恢复前的当前稿"
    assert baseline["document"] == changed["document"]

    restore_record = rows[3]
    assert restore_record["title"].startswith("恢复：")
    assert restore_record["document"] == annotated_version["document"]
    assert restore_record["restoredFromId"] == annotated_version["id"]

    notes = client.get(f"/api/cases/{case['id']}/annotations").json()
    by_id = {row["id"]: row for row in notes}
    assert draft_note["id"] in by_id
    assert by_id[draft_note["id"]]["status"] == "pending"
    assert version_note["id"] in by_id
    fresh = client.get(f"/api/cases/{case['id']}").json()
    assert fresh["document"] == annotated_version["document"]


def test_restored_annotations_keep_discussion_state(client: TestClient) -> None:
    auth = login(client).json()
    case, version = _frozen_version(client, auth, "讨论状态恢复")
    note = _draft_annotation(client, auth, case, "论状态恢复 冻结正", "待回复批注")
    client.post(
        f"/api/cases/{case['id']}/annotations/{note['id']}/replies",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"content": "作者回应：稍后处理"},
    )
    client.patch(
        f"/api/cases/{case['id']}/annotations/{note['id']}/status",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"status": "resolved"},
    )
    _save_content(client, auth, case, "改掉工作稿")
    _draft_annotation(client, auth, case, "掉工作稿", "新批注应被替换")

    restored = _lifecycle(
        client, auth,
        client.get(f"/api/cases/{case['id']}").json(),
        "overwrite", targetId=version["id"],
    )
    assert restored.status_code == 200
    notes = client.get(f"/api/cases/{case['id']}/annotations").json()
    restored_note = [row for row in notes if row["content"] == "待回复批注"]
    assert len(restored_note) == 1
    assert restored_note[0]["status"] == "resolved"
    assert [row["content"] for row in restored_note[0]["replies"]] == ["作者回应：稍后处理"]
    assert not [row for row in notes if row["content"] == "新批注应被替换"]


def test_overwrite_cancel_keeps_current_work_untouched(client: TestClient) -> None:
    auth = login(client).json()
    case, _version = _frozen_version(client, auth, "取消恢复")
    changed = _save_content(client, auth, case, "取消恢复正文")
    _lifecycle(client, auth, changed, "overwrite", targetId="cv-missing")
    fresh = client.get(f"/api/cases/{case['id']}").json()
    assert fresh["document"] == changed["document"]
    assert fresh["revision"] == changed["revision"]
    assert not [
        row for row in _history(client, case["id"])["versions"]
        if row["kind"] in ("manual", "restore")
    ]
