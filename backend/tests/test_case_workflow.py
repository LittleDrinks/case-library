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


def _seed_required_tag_group(client: TestClient) -> None:
    database = client.app.state.database
    database.tag_groups.insert_one(
        {
            "id": "tgg-required-1",
            "name": "投稿必填学科",
            "requiredForSubmission": True,
            "enabled": True,
            "sortKey": 99,
        }
    )
    database.tags.insert_one(
        {
            "id": "tag-required-1",
            "groupId": "tgg-required-1",
            "name": "自然辩证法",
            "sortKey": 1,
        }
    )


def _submit_case(client, owner, case):
    return _transition_json(client, case["id"], owner["csrfToken"], "submit", case)


def _relogin(client, username="user", password="user123"):
    return login(client, username, password).json()


def _review_round(client):
    owner = _relogin(client)
    case = client.get("/api/cases/c-draft-1").json()
    submitted = _submit_case(client, owner, case)
    admin = _relogin(client, "admin", "admin123")
    started = _transition_json(
        client, case["id"], admin["csrfToken"], "start", submitted["case"]
    )
    return admin, case, submitted, started


def _decide(client, admin, started, command, **extra):
    case = started["case"]
    return _transition_json(
        client,
        case["id"],
        admin["csrfToken"],
        command,
        case,
        submittedVersionId=started["version"]["id"],
        **extra,
    )


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
    body = {"title": "新案例", "document": paragraph_document("正文")}

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
    assert created.json()["availableActions"] == ["submit", "snapshot", "rollback"]


def test_new_case_uses_the_required_teaching_template(client: TestClient) -> None:
    auth = login(client, "user", "user123").json()
    created = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "空白案例"},
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
    assert snapshot["case"]["availableActions"] == ["submit", "snapshot", "rollback"]
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
    assert rolled.json()["case"]["availableActions"] == ["submit", "snapshot", "rollback"]


def test_admin_can_hide_and_restore_the_same_published_version(
    client: TestClient,
) -> None:
    admin, approved = publish_seed_case(client)
    case_id = approved["case"]["id"]
    assert approved["case"]["availableActions"] == ["hide"]
    hidden = _transition_json(client, case_id, admin["csrfToken"], "hide", approved["case"])
    assert hidden["case"]["publicationStatus"] == "hidden"
    assert hidden["case"]["workflowStatus"] == "published"
    assert hidden["case"]["publishedVersionId"] == approved["version"]["id"]
    restored = _transition_json(client, case_id, admin["csrfToken"], "restore", hidden["case"])
    assert restored["case"]["publicationStatus"] == "public"
    assert restored["case"]["publishedVersionId"] == approved["version"]["id"]


def test_approval_ends_at_published_without_a_working_draft(
    client: TestClient,
) -> None:
    _admin, approved = publish_seed_case(client)
    case = approved["case"]
    assert case["workflowStatus"] == "published"
    assert case["publicationStatus"] == "public"
    assert case["submittedVersionId"] is None
    assert case["publishedVersionId"] == approved["version"]["id"]
    assert case["availableActions"] == ["hide"]
    login(client, "user", "user123")
    view = client.get("/api/cases/c-draft-1").json()
    assert view["availableActions"] == []
    assert view["ownerId"] == "u-user-demo"


def _assert_withdrawn(withdrawn):
    assert withdrawn["case"]["workflowStatus"] == "draft"
    assert withdrawn["case"]["submittedVersionId"] is None
    assert withdrawn["case"]["lastReview"] is None


def test_owner_withdraws_while_review_is_active(client: TestClient) -> None:
    _admin, case, submitted, started = _review_round(client)
    owner = _relogin(client)
    withdrawn = _transition_json(
        client, case["id"], owner["csrfToken"], "withdraw", started["case"]
    )
    _assert_withdrawn(withdrawn)
    admin = _relogin(client, "admin", "admin123")
    stale = _decide(client, admin, started, "approve")
    assert stale["detail"] == "案例已在其他位置更新"
    owner = _relogin(client)
    resubmitted = _transition_json(
        client, case["id"], owner["csrfToken"], "submit", withdrawn["case"]
    )
    assert resubmitted["case"]["workflowStatus"] == "pending"


def _assert_return_feedback(returned):
    assert returned["case"]["workflowStatus"] == "draft"
    assert "lastReview" not in returned["case"]
    assert returned["event"]["action"] == "reject"
    assert returned["event"]["reasonType"] == "证据不足"
    assert returned["event"]["annotationIds"] == []


def _reject_and_view(client, started):
    admin = _relogin(client, "admin", "admin123")
    returned = _decide(client, admin, started, "reject", reasonType="证据不足")
    _assert_return_feedback(returned)
    admin_view = client.get("/api/cases/c-draft-1").json()
    client.cookies.clear()
    assert client.get("/api/cases/c-draft-1").status_code == 404
    _relogin(client)
    return admin_view, client.get("/api/cases/c-draft-1").json()


def test_reviewer_returns_without_annotations_and_owner_sees_reason(
    client: TestClient,
) -> None:
    _admin, _case, _submitted, started = _review_round(client)
    admin_view, view = _reject_and_view(client, started)
    assert "lastReview" not in admin_view
    history = client.get("/api/cases/c-draft-1/history").json()
    rejects = [event for event in history["events"] if event["action"] == "reject"]
    assert len(rejects) == 1 and rejects[0]["reasonType"] == "证据不足"
    assert view["lastReview"]["action"] == "reject"
    assert view["lastReview"]["reasonType"] == "证据不足"
    assert view["lastReview"]["summary"] == ""
    assert view["availableActions"] == ["submit", "snapshot", "rollback"]


def test_whitespace_only_return_reason_is_rejected(client: TestClient) -> None:
    _admin, case, submitted, started = _review_round(client)
    admin = _relogin(client, "admin", "admin123")
    for reason in ("   ", "\t\n", "\u3000"):
        response = _transition(
            client,
            case["id"],
            admin["csrfToken"],
            "reject",
            started["case"],
            submittedVersionId=submitted["version"]["id"],
            reasonType=reason,
        )
        assert response.status_code == 422


def test_return_reason_is_trimmed_before_persisted(client: TestClient) -> None:
    _admin, _case, _submitted, started = _review_round(client)
    admin = _relogin(client, "admin", "admin123")
    returned = _decide(
        client,
        admin,
        started,
        "supplement",
        reasonType="  证据不足\u3000",
        summary="\n 请补充数据来源。 ",
    )
    assert returned["event"]["reasonType"] == "证据不足"
    assert returned["event"]["summary"] == "请补充数据来源。"
    _relogin(client)
    view = client.get("/api/cases/c-draft-1").json()
    assert view["lastReview"]["reasonType"] == "证据不足"
    assert view["lastReview"]["summary"] == "请补充数据来源。"


def test_return_without_reason_is_rejected(client: TestClient) -> None:
    owner = _relogin(client)
    case = client.get("/api/cases/c-draft-1").json()
    submitted = _submit_case(client, owner, case)
    admin = _relogin(client, "admin", "admin123")
    started = _transition_json(
        client, case["id"], admin["csrfToken"], "start", submitted["case"]
    )
    response = _transition(
        client,
        case["id"],
        admin["csrfToken"],
        "reject",
        started["case"],
        submittedVersionId=submitted["version"]["id"],
    )
    assert response.status_code == 422


def test_resubmit_clears_the_last_review_feedback(client: TestClient) -> None:
    _admin, case, _submitted, started = _review_round(client)
    admin = _relogin(client, "admin", "admin123")
    returned = _decide(client, admin, started, "supplement", reasonType="证据不足")
    owner = _relogin(client)
    resubmitted = _transition_json(
        client, case["id"], owner["csrfToken"], "submit", returned["case"]
    )
    assert resubmitted["case"]["workflowStatus"] == "pending"
    assert resubmitted["case"]["lastReview"] is None


def _create_empty_case(client, owner, title):
    document = {"type": "doc", "content": [{"type": "paragraph"}]}
    return client.post(
        "/api/cases",
        headers={"X-CSRF-Token": owner["csrfToken"]},
        json={"title": title, "document": document},
    ).json()


def _save_body(client, owner, case, text):
    return client.patch(
        f"/api/cases/{case['id']}",
        headers={"X-CSRF-Token": owner["csrfToken"]},
        json={"document": paragraph_document(text), "revision": case["revision"]},
    ).json()


def _assert_missing_group(response):
    assert response.status_code == 422
    assert "必填标签组未选择标签：投稿必填学科" in response.json()["detail"]


def test_submit_requires_nonempty_body_and_required_tag_groups(
    client: TestClient,
) -> None:
    owner = _relogin(client)
    _seed_required_tag_group(client)
    case = _create_empty_case(client, owner, "标签案例")
    blocked = _transition(client, case["id"], owner["csrfToken"], "submit", case)
    assert "正文不能为空" in blocked.json()["detail"]
    _assert_missing_group(blocked)
    saved = _save_body(client, owner, case, "补齐正文")
    _assert_missing_group(
        _transition(client, case["id"], owner["csrfToken"], "submit", saved)
    )
    database = client.app.state.database
    database.cases.update_one({"id": case["id"]}, {"$set": {"tagIds": ["tag-required-1"]}})
    current = client.get(f"/api/cases/{case['id']}").json()
    accepted = _transition_json(client, case["id"], owner["csrfToken"], "submit", current)
    assert accepted["case"]["workflowStatus"] == "pending"
    assert accepted["version"]["metadata"]["tagIds"] == ["tag-required-1"]


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
