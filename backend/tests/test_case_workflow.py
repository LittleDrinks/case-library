from __future__ import annotations

import hashlib

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


def _save_content(client, auth: dict, case: dict, text: str, title: str | None = None):
    body = {"document": paragraph_document(text), "revision": case["revision"]}
    if title is not None:
        body["title"] = title
    response = client.patch(
        f"/api/cases/{case['id']}",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json=body,
    )
    assert response.status_code == 200
    return response.json()


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
    owner = login(client, "user", "user123").json()
    return _transition(client, case["id"], owner["csrfToken"], "reopen", hidden["case"])


def _seed_required_tag_group(client: TestClient) -> None:
    database = client.app.state.database
    database.tag_groups.insert_one({
        "id": "tgg-required-1",
        "name": "投稿必填学科",
        "requiredForSubmission": True,
        "enabled": True,
        "sortKey": 99,
    })
    database.tags.insert_one({
        "id": "tag-required-1",
        "groupId": "tgg-required-1",
        "name": "自然辩证法",
        "sortKey": 1,
    })


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


def _expected_admin_view() -> dict:
    return {
        "id": "u-admin-demo",
        "username": "admin",
        "name": "演示管理员",
        "role": "admin",
        "mustChangePassword": False,
        "campusVerified": True,
    }


def test_user_can_login_and_restore_session(client: TestClient) -> None:
    response = login(client)

    assert response.status_code == 200
    assert response.json()["user"] == _expected_admin_view()
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
    assert created.json()["availableActions"] == ["submit", "overwrite"]


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


OVERWRITE_HEADING = "一、教学说明"


def _annotated_document(text: str) -> dict:
    return {
        "type": "doc",
        "content": [
            {"type": "heading", "attrs": {"level": 1}, "content": [{"type": "text", "text": OVERWRITE_HEADING}]},
            {"type": "paragraph", "content": [{"type": "text", "text": text}]},
        ],
    }


def _freeze_and_reopen(client, auth: dict, case: dict, text: str, title: str):
    """投稿冻结一个历史版本，再撤回并改掉当前稿；返回（工作稿，已建版本）。"""
    saved = _save_content(client, auth, case, text, title)
    submitted = _transition_json(client, case["id"], auth["csrfToken"], "submit", saved)
    reopened = _transition_json(client, case["id"], auth["csrfToken"], "withdraw", submitted["case"])
    return reopened["case"], submitted


def _overwrite_version(client, auth: dict, case: dict, changed: dict, version: dict):
    return _transition(
        client, case["id"], auth["csrfToken"], "overwrite", changed, targetId=version["id"],
    )


def _insert_internal_version(client, version: dict) -> dict:
    internal = {
        **version,
        "id": "ai-internal-1",
        "kind": "pre_agent_write",
        "number": 99,
    }
    client.app.state.database.case_versions.insert_one(internal)
    return internal


def test_author_overwrites_draft_with_a_history_version(client: TestClient) -> None:
    auth = login(client, "user", "user123").json()
    case = client.get("/api/cases/c-draft-1").json()
    reopened, submitted = _freeze_and_reopen(client, auth, case, "冻结正文", "投稿标题")
    changed = _save_content(client, auth, reopened, "覆盖前草稿正文", "覆盖前标题")
    overwritten = _overwrite_version(client, auth, case, changed, submitted["version"]).json()

    assert overwritten["case"]["title"] == "投稿标题"
    assert document_text(overwritten["case"]["document"]) == "冻结正文"
    assert overwritten["case"]["availableActions"] == ["submit", "overwrite"]
    history = client.get("/api/cases/c-draft-1/history").json()
    assert [row["number"] for row in history["versions"]] == [1]
    assert history["versions"][0]["id"] == submitted["version"]["id"]
    assert history["versions"][0]["document"] == submitted["version"]["document"]


def _review_round_with_annotations(client, created: dict, owner: dict):
    """投稿→开审→版本批注→撤回；返回（撤回工作稿，投稿版本，两批批注）。"""
    draft_note = _draft_annotation(client, owner, created)
    submitted = _transition_json(client, created["id"], owner["csrfToken"], "submit", created)
    admin = _relogin(client, "admin", "admin123")
    started = _transition_json(client, created["id"], admin["csrfToken"], "start", submitted["case"])
    version_note = _version_annotation(client, admin, started)
    owner = login(client, "user", "user123").json()
    reopened = _transition_json(client, created["id"], owner["csrfToken"], "withdraw", started["case"])
    return reopened["case"], submitted, draft_note, version_note, owner


def test_overwrite_clears_draft_annotations_but_keeps_version_ones(client: TestClient) -> None:
    owner = login(client, "user", "user123").json()
    created = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": owner["csrfToken"]},
        json={"title": "覆盖批注案例", "document": _annotated_document("工作稿正文")},
    ).json()
    reopened, submitted, draft_note, version_note, owner = _review_round_with_annotations(
        client, created, owner,
    )
    changed = _save_content(client, owner, reopened, "覆盖前草稿正文", "覆盖前标题")
    _overwrite_version(client, owner, created, changed, submitted["version"])

    remaining = client.get(f"/api/cases/{created['id']}/annotations").json()
    ids = [row["id"] for row in remaining]
    assert draft_note["id"] not in ids
    assert version_note["id"] in ids


def _draft_annotation(client, owner: dict, case: dict) -> dict:
    quote = "工作稿正文"
    start = len(OVERWRITE_HEADING) + 3
    note = client.post(
        f"/api/cases/{case['id']}/annotations",
        headers={"X-CSRF-Token": owner["csrfToken"]},
        json={
            "quote": quote, "section": OVERWRITE_HEADING, "content": "工作稿旧批注",
            "source": "manual", "revision": case["revision"],
            "from": start, "to": start + len(quote),
            "quoteHash": hashlib.sha256(quote.encode()).hexdigest(),
        },
    )
    assert note.status_code == 201
    return note.json()


def _version_annotation(client, admin: dict, started: dict) -> dict:
    note = client.post(
        f"/api/cases/{started['case']['id']}/annotations",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={
            "quote": "工作稿正文", "section": OVERWRITE_HEADING,
            "content": "待审版本批注", "source": "admin",
        },
    )
    assert note.status_code == 201
    return note.json()


def _other_case_version(client, auth: dict) -> dict:
    other = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "另一案例", "document": paragraph_document("其他案例正文")},
    ).json()
    return _transition_json(client, other["id"], auth["csrfToken"], "submit", other)


def test_overwrite_rejects_cross_case_and_unknown_targets(client: TestClient) -> None:
    auth = login(client, "user", "user123").json()
    case = client.get("/api/cases/c-draft-1").json()
    submitted = _other_case_version(client, auth)
    cross_case = _overwrite_version(client, auth, case, case, submitted["version"])
    unknown = _transition(
        client, case["id"], auth["csrfToken"], "overwrite", case, targetId="cv-missing",
    )

    assert cross_case.status_code == 404
    assert unknown.status_code == 404
    current = client.get("/api/cases/c-draft-1").json()
    assert current["revision"] == case["revision"]
    assert current["document"] == case["document"]


def test_history_and_overwrite_ignore_internal_versions(client: TestClient) -> None:
    auth = login(client, "user", "user123").json()
    case = client.get("/api/cases/c-draft-1").json()
    submitted = _transition_json(client, case["id"], auth["csrfToken"], "submit", case)
    internal = _insert_internal_version(client, submitted["version"])

    history = client.get(f"/api/cases/{case['id']}/history")
    assert [row["id"] for row in history.json()["versions"]] == [submitted["version"]["id"]]

    reopened = _transition_json(client, case["id"], auth["csrfToken"], "withdraw", submitted["case"])
    rejected = _overwrite_version(client, auth, case, reopened["case"], internal)
    assert rejected.status_code == 404


def test_overwrite_requires_owner_draft_and_current_revision(client: TestClient) -> None:
    owner = login(client, "user", "user123").json()
    case = client.get("/api/cases/c-draft-1").json()
    admin = login(client).json()
    stranger = _transition(client, case["id"], admin["csrfToken"], "overwrite", case, targetId="cv-x")
    assert stranger.status_code == 403

    owner = login(client, "user", "user123").json()
    stale = _transition(
        client, case["id"], owner["csrfToken"], "overwrite",
        {**case, "revision": case["revision"] + 9}, targetId="cv-x",
    )
    assert stale.status_code == 409

    submitted = _transition_json(client, case["id"], owner["csrfToken"], "submit", case)
    frozen = _transition(
        client, case["id"], owner["csrfToken"], "overwrite", submitted["case"], targetId="cv-x",
    )
    assert frozen.status_code == 409


def test_removed_manual_version_commands_are_rejected(client: TestClient) -> None:
    auth = login(client, "user", "user123").json()
    case = client.get("/api/cases/c-draft-1").json()

    assert _transition(client, case["id"], auth["csrfToken"], "snapshot", case).status_code == 422
    assert _transition(client, case["id"], auth["csrfToken"], "rollback", case).status_code == 422


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


def test_admin_author_hidden_case_actions_are_unique(client: TestClient) -> None:
    admin = login(client).json()
    case = client.get("/api/cases/c-02").json()
    hidden = _transition_json(client, case["id"], admin["csrfToken"], "hide", case)
    assert hidden["case"]["availableActions"] == ["reopen", "restore"]


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
    assert view["availableActions"] == ["reopen"]
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
    assert view["availableActions"] == ["submit", "overwrite"]


def _review_annotation(client, admin, case):
    response = client.post(
        f"/api/cases/{case['id']}/annotations",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={
            "quote": "供应中断周期不明",
            "section": "情境设定与前提假设",
            "content": "请明确对应的课程目标。",
            "source": "admin",
        },
    )
    assert response.status_code == 201
    return response.json()


def _mine_card(client, case_id):
    rows = client.get("/api/cases?scope=mine").json()
    return next(row for row in rows if row["id"] == case_id)


def test_mine_list_surfaces_return_feedback_until_resubmit(client: TestClient) -> None:
    _admin, case, _submitted, started = _review_round(client)
    admin = _relogin(client, "admin", "admin123")
    _review_annotation(client, admin, started["case"])
    _decide(client, admin, started, "reject", reasonType="证据不足")
    owner = _relogin(client)
    card = _mine_card(client, case["id"])
    assert card["lastReview"]["action"] == "reject"
    assert card["lastReview"]["reasonType"] == "证据不足"
    assert card["pendingAnnotationCount"] == 1
    owner = _relogin(client)
    current = client.get(f"/api/cases/{case['id']}").json()
    _submit_case(client, owner, current)
    card = _mine_card(client, case["id"])
    assert card["lastReview"] is None
    assert card["pendingAnnotationCount"] == 0


def test_public_views_never_expose_review_feedback(client: TestClient) -> None:
    _admin, approved = publish_seed_case(client)
    public = client.get("/api/cases/c-draft-1/public").json()
    assert "lastReview" not in public
    assert "pendingAnnotationCount" not in public
    assert approved["case"]["workflowStatus"] == "published"


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


def test_owner_reopens_a_hidden_case_without_exposing_the_working_copy(
    client: TestClient,
) -> None:
    admin, approved = publish_seed_case(client)
    reopened = reopen_hidden_case(client, admin, approved)
    assert reopened.status_code == 200
    assert reopened.json()["case"]["workflowStatus"] == "draft"
    assert reopened.json()["case"]["publicationStatus"] == "hidden"
    assert reopened.json()["case"]["submittedVersionId"] is None


def test_owner_reopens_public_case_and_republishes_a_new_default(client: TestClient) -> None:
    admin, first = publish_seed_case(client)
    assert _transition(client, first["case"]["id"], admin["csrfToken"], "reopen", first["case"]).status_code == 409
    owner = login(client, "user", "user123").json()
    reopened = _transition_json(client, first["case"]["id"], owner["csrfToken"], "reopen", first["case"])
    assert reopened["case"]["publishedVersionId"] == first["version"]["id"]
    assert client.get("/api/cases/c-draft-1/public").json()["title"] == first["version"]["title"]
    saved = _save_title(client, owner, reopened["case"], "第二版标题")
    submitted = _transition_json(client, first["case"]["id"], owner["csrfToken"], "submit", saved)
    assert client.get("/api/cases/c-draft-1/public").json()["title"] == first["version"]["title"]
    admin = login(client).json()
    started = _transition_json(client, first["case"]["id"], admin["csrfToken"], "start", submitted["case"])
    assert client.get("/api/cases/c-draft-1/public").json()["title"] == first["version"]["title"]
    approved = _transition_json(client, first["case"]["id"], admin["csrfToken"], "approve", started["case"], submittedVersionId=submitted["version"]["id"])
    assert approved["case"]["publishedVersionId"] == submitted["version"]["id"]
    assert approved["case"]["submittedVersionId"] is None
    assert client.get("/api/cases/c-draft-1/public").json()["title"] == "第二版标题"


def test_logout_revokes_the_session(client: TestClient) -> None:
    auth = login(client).json()
    response = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": auth["csrfToken"]},
    )

    assert response.status_code == 204
    assert client.get("/api/auth/session").status_code == 401
