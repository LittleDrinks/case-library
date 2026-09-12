"""小颗粒度历史版本闭环（Issue #293）：手动版本、恢复保留批注、AI 候选独立成稿。"""

from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from app.modules.agent import prosemirror
from app.modules.agent.runtime import agent
from tests.test_annotation_discussion import create_annotation
from tests.test_annotation_agent import _proposal_model, _send, _wait_terminal


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


def _manual_version_fixture(client, auth):
    case = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "手动版本案例", "document": paragraph_document("手动正文")},
    ).json()
    saved = _save_content(client, auth, case, "手动正文 第二版")
    return case, saved


def _create_manual_version(client, auth, case, saved):
    return client.post(
        f"/api/cases/{case['id']}/versions",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "补充教学目标", "revision": saved["revision"]},
    )


def _assert_manual_version(client, case, saved, created) -> None:
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


def test_author_creates_named_manual_version(client: TestClient) -> None:
    auth = login(client).json()
    case, saved = _manual_version_fixture(client, auth)
    created = _create_manual_version(client, auth, case, saved)
    _assert_manual_version(client, case, saved, created)
    stale = client.post(
        f"/api/cases/{case['id']}/versions",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "旧页签", "revision": saved["revision"]},
    )
    assert stale.status_code == 409


def _annotation_case(client, auth):
    case = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "批注快照案例", "document": heading_document("批注正文")},
    ).json()
    annotation = create_annotation(client, auth, case, "批注正文")
    return case, annotation


def _real_ai_revision(client, auth, case, annotation):
    with agent.override(model=_proposal_model("保留修订集合")):
        response = _send(client, auth, case, annotation, "请保留这条修订")
    assert response.status_code == 200, response.text
    _wait_terminal(client, case["id"])
    database = client.app.state.database
    live = database.annotations.find_one({"id": annotation["id"]}, {"_id": 0})
    assert live and live["revisions"], live
    revision = live["revisions"][0]
    artifact = database.agent_artifacts.find_one({"id": revision["artifactId"]}, {"_id": 0})
    assert artifact and artifact["annotationId"] == annotation["id"]
    assert revision["runId"] == artifact["runId"]
    return database, live, artifact


def _formal_version_copy(client, auth, case, database, live, artifact):
    created = client.post(
        f"/api/cases/{case['id']}/versions",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "批注快照", "revision": case["revision"]},
    )
    assert created.status_code == 200
    version = created.json()
    assert version["annotations"][0]["revisions"][0]["artifactId"] == artifact["id"]
    assert database.annotations.count_documents({"caseId": case["id"], "versionId": version["id"]}) == 0
    assert database.annotations.find_one(
        {"id": live["id"], "versionId": None}, {"_id": 0},
    )
    return version


def _reject_ai_artifact(client, auth, case, artifact) -> None:
    snapshot = client.get(f"/api/cases/{case['id']}/agent/thread").json()
    rejected = client.post(
        f"/api/cases/{case['id']}/agent/thread/{snapshot['id']}/artifacts/"
        f"{artifact['id']}/decision",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"decision": "rejected"},
    )
    assert rejected.status_code == 200, rejected.text


def test_formal_version_keeps_independent_annotation_revisions(client: TestClient) -> None:
    auth = login(client).json()
    case, annotation = _annotation_case(client, auth)
    database, live, artifact = _real_ai_revision(client, auth, case, annotation)
    version = _formal_version_copy(client, auth, case, database, live, artifact)
    _reject_ai_artifact(client, auth, case, artifact)
    live_after = database.annotations.find_one({"id": annotation["id"]}, {"_id": 0})
    assert live_after["revisions"][0]["status"] == "rejected"
    historical = next(
        row for row in _history(client, case["id"])["versions"]
        if row["id"] == version["id"]
    )
    assert historical["annotations"][0]["revisions"] == version["annotations"][0]["revisions"]


def _create_private_snapshot(client, auth, case, annotation, database):
    replied = client.post(
        f"/api/cases/{case['id']}/annotations/{annotation['id']}/replies",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"content": "快照中的作者回复"},
    )
    assert replied.status_code == 200, replied.text
    created = client.post(
        f"/api/cases/{case['id']}/versions",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "私人批注快照", "revision": case["revision"]},
    )
    assert created.status_code == 200, created.text
    version = created.json()
    snapshot = version["annotations"][0]
    assert snapshot["replies"][0]["content"] == "快照中的作者回复"
    assert database.annotations.count_documents({"caseId": case["id"], "versionId": version["id"]}) == 0
    return version, snapshot


def _assert_admin_cannot_read_private_snapshot(client, case, version):
    admin = login(client, "admin", "admin123").json()
    listed = client.get(
        f"/api/cases/{case['id']}/annotations", headers={"X-CSRF-Token": admin["csrfToken"]},
    )
    assert listed.status_code == 200 and listed.json() == []
    admin_history = client.get(
        f"/api/cases/{case['id']}/history", headers={"X-CSRF-Token": admin["csrfToken"]},
    )
    assert admin_history.status_code == 200
    admin_version = next(row for row in admin_history.json()["versions"] if row["id"] == version["id"])
    assert admin_version["annotations"] == []
    return admin


def _delete_current_annotation(client, auth, case, annotation):
    changed = client.patch(
        f"/api/cases/{case['id']}/annotations/{annotation['id']}",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"content": "当前批注已被修改"},
    )
    assert changed.status_code == 200, changed.text
    deleted = client.delete(
        f"/api/cases/{case['id']}/annotations/{annotation['id']}",
        headers={"X-CSRF-Token": auth["csrfToken"]},
    )
    assert deleted.status_code in (200, 204), deleted.text


def _assert_restored_snapshot(client, database, case, annotation, version, snapshot):
    current = client.get(f"/api/cases/{case['id']}").json()
    auth = login(client).json()
    restored = _lifecycle(client, auth, current, "overwrite", targetId=version["id"])
    assert restored.status_code == 200, restored.text
    restored_rows = client.get(f"/api/cases/{case['id']}/annotations").json()
    restored_note = next(row for row in restored_rows if row["content"] == snapshot["content"])
    assert restored_note["id"] != annotation["id"]
    assert restored_note["restoredFromId"] == snapshot["id"]
    assert restored_note.get("versionId") is None
    assert restored_note["replies"] == snapshot["replies"]
    restored_document = database.annotations.find_one(
        {"id": restored_note["id"]}, {"_id": 0},
    )
    assert restored_document["revisions"] == snapshot["revisions"]


def test_private_snapshot_stays_private_and_restores_after_current_delete(
    client: TestClient,
) -> None:
    auth = login(client).json()
    case, annotation = _annotation_case(client, auth)
    database, _live, _artifact = _real_ai_revision(client, auth, case, annotation)
    version, snapshot = _create_private_snapshot(client, auth, case, annotation, database)
    _assert_admin_cannot_read_private_snapshot(client, case, version)
    auth = login(client).json()
    _delete_current_annotation(client, auth, case, annotation)
    historical = next(row for row in _history(client, case["id"])["versions"] if row["id"] == version["id"])
    assert historical["annotations"] == version["annotations"]
    _assert_restored_snapshot(client, database, case, annotation, version, snapshot)


def _assert_manual_version_owner_only(client, case) -> None:
    admin = login(client, "admin", "admin123").json()
    stranger = client.post(
        f"/api/cases/{case['id']}/versions",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={"title": "管理员代建", "revision": case["revision"]},
    )
    assert stranger.status_code == 403


def _assert_manual_version_requires_draft(client, case) -> None:
    owner = login(client).json()
    submitted = _lifecycle(client, owner, case, "submit").json()
    frozen = client.post(
        f"/api/cases/{case['id']}/versions",
        headers={"X-CSRF-Token": owner["csrfToken"]},
        json={"title": "冻结中创建", "revision": submitted["case"]["revision"]},
    )
    assert frozen.status_code == 409


def test_manual_version_requires_owner_and_draft(client: TestClient) -> None:
    auth = login(client).json()
    case = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "权限案例", "document": paragraph_document("权限正文")},
    ).json()
    _assert_manual_version_owner_only(client, case)
    _assert_manual_version_requires_draft(client, case)


def _restore_current_work(client, auth):
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
    return case, changed, annotated_version, draft_note, version_note


def _assert_restore_history(
    client, case, changed, annotated_version, draft_note, version_note,
) -> None:
    rows = _history(client, case["id"])["versions"]
    kinds = [row["kind"] for row in rows]
    assert kinds == ["submission", "submission", "manual", "restore"]
    baseline = rows[2]
    assert baseline["title"] == "恢复前的当前稿"
    assert baseline["document"] == changed["document"]
    assert baseline["annotations"][0]["id"] == draft_note["id"]
    restore_record = rows[3]
    assert restore_record["title"].startswith("恢复：")
    assert restore_record["document"] == annotated_version["document"]
    assert restore_record["restoredFromId"] == annotated_version["id"]
    restored = {row["restoredFromId"]: row for row in restore_record["annotations"]}
    assert restored[draft_note["id"]]["id"] != draft_note["id"]
    assert restored[version_note["id"]]["id"] != version_note["id"]


def _assert_restored_submission_annotations(client, case, draft_note, version_note) -> None:
    notes = client.get(f"/api/cases/{case['id']}/annotations").json()
    by_id = {row["id"]: row for row in notes}
    assert draft_note["id"] not in by_id
    assert version_note["id"] in by_id
    restored = {
        row["restoredFromId"]: row for row in by_id.values()
        if row.get("restoredFromId")
    }
    restored_draft = restored[draft_note["id"]]
    restored_review = restored[version_note["id"]]
    assert restored_draft["id"] != draft_note["id"]
    assert restored_review["id"] != version_note["id"]
    assert restored_draft.get("versionId") is None
    assert restored_review.get("versionId") is None


def test_restore_keeps_current_work_and_appends_restore_record(client: TestClient) -> None:
    auth = login(client).json()
    case, changed, annotated_version, draft_note, version_note = _restore_current_work(
        client, auth,
    )
    _assert_restore_history(
        client, case, changed, annotated_version, draft_note, version_note,
    )
    _assert_restored_submission_annotations(client, case, draft_note, version_note)
    fresh = client.get(f"/api/cases/{case['id']}").json()
    assert fresh["document"] == annotated_version["document"]


def _resolve_discussion(client, auth, case, note) -> None:
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


def _restore_discussion(client, auth, case, version):
    case = _save_content(client, auth, case, "改掉工作稿")
    new_note = _draft_annotation(client, auth, case, "掉工作稿", "新批注应被保存到恢复前版本")
    restored = _lifecycle(
        client, auth,
        client.get(f"/api/cases/{case['id']}").json(),
        "overwrite", targetId=version["id"],
    )
    assert restored.status_code == 200
    return client.get(f"/api/cases/{case['id']}/annotations").json(), new_note


def _discussion_restore_fixture(client, auth):
    case, version = _frozen_version(client, auth, "讨论状态恢复")
    note = _draft_annotation(client, auth, case, "论状态恢复 冻结正", "待回复批注")
    _resolve_discussion(client, auth, case, note)
    current = client.get(f"/api/cases/{case['id']}").json()
    created = client.post(
        f"/api/cases/{case['id']}/versions",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "讨论状态快照", "revision": current["revision"]},
    )
    assert created.status_code == 200, created.text
    current = client.get(f"/api/cases/{case['id']}").json()
    return _restore_discussion(client, auth, current, created.json())


def test_restored_annotations_keep_discussion_state(client: TestClient) -> None:
    auth = login(client).json()
    notes, new_note = _discussion_restore_fixture(client, auth)
    restored_note = [row for row in notes if row["content"] == "待回复批注"]
    assert len(restored_note) == 1
    assert restored_note[0]["status"] == "resolved"
    assert [row["content"] for row in restored_note[0]["replies"]] == ["作者回应：稍后处理"]
    assert not [row for row in notes if row["id"] == new_note["id"]]


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
