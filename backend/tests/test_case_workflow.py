from __future__ import annotations

from fastapi.testclient import TestClient


def login(client: TestClient, username: str = "admin", password: str = "admin123"):
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )


def paragraph_document(text: str) -> dict:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def document_text(document: dict) -> str:
    return "\n".join(
        inline.get("text", "")
        for node in document["content"]
        for inline in node.get("content", [])
    )


def lifecycle(client: TestClient, case_id: str, csrf: str, body: dict):
    return client.post(
        f"/api/cases/{case_id}/lifecycle",
        headers={"X-CSRF-Token": csrf},
        json=body,
    )


def _transition(client, case_id: str, csrf: str, command: str, case: dict, **extra):
    body = {"command": command, "revision": case["revision"], **extra}
    return lifecycle(client, case_id, csrf, body)


def _transition_json(
    client, case_id: str, csrf: str, command: str, case: dict, **extra
) -> dict:
    return _transition(client, case_id, csrf, command, case, **extra).json()


def _save_title(client: TestClient, auth: dict, case: dict, title: str) -> dict:
    return client.patch(
        "/api/cases/c-draft-1",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": title, "revision": case["revision"]},
    ).json()


def publish_seed_case(client: TestClient) -> tuple[dict, dict]:
    owner = login(client, "user", "user123").json()
    case = client.get("/api/cases/c-draft-1").json()
    submitted = _transition_json(client, case["id"], owner["csrfToken"], "submit", case)
    admin = login(client).json()
    started = _transition_json(
        client, case["id"], admin["csrfToken"], "start", submitted["case"]
    )
    approved = _transition_json(
        client,
        case["id"],
        admin["csrfToken"],
        "approve",
        started["case"],
        submittedVersionId=submitted["version"]["id"],
    )
    return admin, approved


def reopen_hidden_case(client: TestClient, admin: dict, approved: dict):
    case = approved["case"]
    hidden = _transition_json(client, case["id"], admin["csrfToken"], "hide", case)
    return _transition(client, case["id"], admin["csrfToken"], "reopen", hidden["case"])


def test_user_can_login_and_restore_session(client: TestClient) -> None:
    response = login(client)

    assert response.status_code == 200
    assert response.json()["user"] == {
        "id": "u-admin-demo",
        "username": "admin",
        "name": "演示管理员",
        "role": "admin",
        "mustChangePassword": False,
    }
    assert response.json()["csrfToken"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]

    restored = client.get("/api/auth/session")

    assert restored.status_code == 200
    assert restored.json() == response.json()


def test_author_can_save_and_refresh_a_prosemirror_document(client: TestClient) -> None:
    auth = login(client, "user", "user123").json()
    original = client.get("/api/cases/c-draft-1").json()
    document = paragraph_document("刷新后仍然存在的正文")

    saved = client.patch(
        "/api/cases/c-draft-1",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={
            "title": "已保存案例",
            "document": document,
            "revision": original["revision"],
        },
    )

    assert saved.status_code == 200
    assert saved.json()["revision"] == original["revision"] + 1
    assert saved.json()["document"] == document
    assert client.get("/api/cases/c-draft-1").json() == saved.json()


def test_stale_revision_is_rejected_with_current_revision(client: TestClient) -> None:
    auth = login(client, "user", "user123").json()
    original = client.get("/api/cases/c-draft-1").json()
    headers = {"X-CSRF-Token": auth["csrfToken"]}
    first = {"title": "先保存", "revision": original["revision"]}
    stale = {"title": "后到的旧页面", "revision": original["revision"]}

    assert (
        client.patch("/api/cases/c-draft-1", headers=headers, json=first).status_code
        == 200
    )
    response = client.patch("/api/cases/c-draft-1", headers=headers, json=stale)

    assert response.status_code == 409
    assert response.json() == {"detail": "案例已在其他位置更新", "currentRevision": 2}


def test_admin_cannot_edit_an_authors_working_version(client: TestClient) -> None:
    auth = login(client).json()
    current = client.get("/api/cases/c-draft-1").json()
    response = client.patch(
        "/api/cases/c-draft-1",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "管理员代改", "revision": current["revision"]},
    )

    assert response.status_code == 403


def test_case_creation_requires_csrf(client: TestClient) -> None:
    auth = login(client, "user", "user123").json()
    body = {"stageId": "ug", "typeId": "ct-figure", "templateId": "tpl-general-v1"}

    assert client.post("/api/cases", json=body).status_code == 403
    created = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json=body,
    )

    assert created.status_code == 200
    assert created.json()["revision"] == 1
    assert created.json()["workflowStatus"] == "draft"
    assert created.json()["publicationStatus"] == "none"


def test_new_case_uses_the_required_teaching_template(client: TestClient) -> None:
    auth = login(client, "user", "user123").json()
    created = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={
            "stageId": "ug",
            "typeId": "ct-figure",
            "templateId": "tpl-teaching-standard-v1",
        },
    )
    text = document_text(created.json()["document"])

    assert created.status_code == 200
    assert "一、教学说明（800字左右）" in text
    assert "（二）阅读思考题（2～3个）" in text
    assert "二、文本内容（2500字左右）" in text
    assert "三、附件" in text


def test_author_can_snapshot_and_rollback_a_working_version(client: TestClient) -> None:
    auth = login(client, "user", "user123").json()
    case = client.get("/api/cases/c-draft-1").json()
    saved = _save_title(client, auth, case, "快照基线")
    snapshot = _transition_json(
        client, case["id"], auth["csrfToken"], "snapshot", saved
    )
    changed = _save_title(client, auth, saved, "回滚前")
    rolled = _transition(
        client,
        case["id"],
        auth["csrfToken"],
        "rollback",
        changed,
        targetId=snapshot["snapshot"]["id"],
    )
    assert rolled.status_code == 200 and rolled.json()["case"]["title"] == "快照基线"


def test_admin_can_hide_and_restore_the_same_published_version(
    client: TestClient,
) -> None:
    admin, approved = publish_seed_case(client)
    hidden = _transition(
        client, approved["case"]["id"], admin["csrfToken"], "hide", approved["case"]
    )
    assert hidden.status_code == 200
    assert hidden.json()["case"]["publicationStatus"] == "hidden"
    assert hidden.json()["case"]["publishedVersionId"] == approved["version"]["id"]
    restored = _transition(
        client,
        approved["case"]["id"],
        admin["csrfToken"],
        "restore",
        hidden.json()["case"],
    )
    assert restored.status_code == 200
    assert restored.json()["case"]["publicationStatus"] == "public"


def test_admin_reopens_a_hidden_case_without_exposing_the_working_copy(
    client: TestClient,
) -> None:
    admin, approved = publish_seed_case(client)
    reopened = reopen_hidden_case(client, admin, approved)
    assert reopened.status_code == 200
    assert reopened.json()["case"]["workflowStatus"] == "draft"
    assert reopened.json()["case"]["publicationStatus"] == "hidden"
    assert reopened.json()["case"]["submittedVersionId"] is None
    retry = _transition(
        client,
        approved["case"]["id"],
        admin["csrfToken"],
        "restore",
        reopened.json()["case"],
    )
    assert retry.status_code == 409


def test_logout_revokes_the_session(client: TestClient) -> None:
    auth = login(client).json()
    response = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": auth["csrfToken"]},
    )

    assert response.status_code == 204
    assert client.get("/api/auth/session").status_code == 401
