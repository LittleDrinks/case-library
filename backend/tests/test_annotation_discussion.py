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
    content = [{
        "type": "heading", "attrs": {"level": 1},
        "content": [{"type": "text", "text": HEADING}],
    }]
    content.extend(
        {"type": "paragraph", "content": [{"type": "text", "text": text}]}
        for text in paragraphs
    )
    return {"type": "doc", "content": content}


def paragraph_start(*prior: str) -> int:
    return len(HEADING) + 3 + sum(len(text) + 2 for text in prior)


def create_case(client: TestClient, user: dict, *paragraphs: str) -> dict:
    response = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": user["csrfToken"]},
        json={"title": "批注讨论测试", "document": document(*paragraphs)},
    )
    assert response.status_code == 200
    return response.json()


def create_annotation(client: TestClient, user: dict, case: dict, text: str) -> dict:
    start = paragraph_start()
    response = client.post(
        f"/api/cases/{case['id']}/annotations",
        headers={"X-CSRF-Token": user["csrfToken"]},
        json={
            "from": start,
            "to": start + len(text),
            "quote": text,
            "section": HEADING,
            "quoteHash": hashlib.sha256(text.encode()).hexdigest(),
            "revision": case["revision"],
            "content": "请补充评价依据。",
            "source": "manual",
        },
    )
    assert response.status_code == 201
    return response.json()


def seed_revisions(client: TestClient, annotation: dict, *replacements: str) -> None:
    seed_linked_revisions(client, annotation, *replacements)


def _linked_target(annotation: dict) -> dict:
    return {"from": annotation["from"], "to": annotation["to"], "quote": annotation["quote"]}


def _linked_artifact(annotation: dict, thread_id: str, run_id: str,
                     artifact_id: str, replacement: str) -> dict:
    return {
        "id": artifact_id, "caseId": annotation["caseId"], "threadId": thread_id,
        "runId": run_id, "status": "pending", "baseRevision": annotation["revision"],
        "target": _linked_target(annotation), "annotationId": annotation["id"],
        "replacement": replacement, "reason": "修订理由", "sources": [],
        "createdAt": "2026-09-11T00:00:00Z",
    }


def _linked_revision(annotation: dict, artifact_id: str, run_id: str,
                     index: int, replacement: str) -> dict:
    return {
        "id": f"arv-{index}", "artifactId": artifact_id, "runId": run_id,
        "baseRevision": annotation["revision"], "target": _linked_target(annotation),
        "replacement": replacement, "reason": "修订理由", "status": "pending",
        "createdBy": annotation["createdBy"], "createdAt": "2026-09-11T00:00:00Z",
    }


def _seed_linked_candidate(database, annotation: dict, thread_id: str,
                            index: int, replacement: str) -> tuple[str, dict]:
    artifact_id, run_id = f"artifact-{index}", f"run-{index}"
    database.agent_runs.insert_one({"id": run_id, "threadId": thread_id, "status": "completed"})
    database.agent_artifacts.insert_one(
        _linked_artifact(annotation, thread_id, run_id, artifact_id, replacement)
    )
    return artifact_id, _linked_revision(annotation, artifact_id, run_id, index, replacement)


def seed_linked_revisions(client: TestClient, annotation: dict, *replacements: str) -> list[str]:
    database = client.app.state.database
    thread_id = f"thread-{annotation['id']}"
    database.agent_threads.insert_one({
        "id": thread_id, "caseId": annotation["caseId"],
        "ownerId": annotation["createdBy"], "eventSeq": 0,
    })
    revisions, artifact_ids = [], []
    for index, replacement in enumerate(replacements, 1):
        artifact_id, revision = _seed_linked_candidate(
            database, annotation, thread_id, index, replacement
        )
        artifact_ids.append(artifact_id)
        revisions.append(revision)
    database.annotations.update_one(
        {"id": annotation["id"]}, {"$set": {"revisions": revisions}}
    )
    return artifact_ids


def save_document(client: TestClient, user: dict, case: dict, next_document: dict, steps: list[dict]):
    return client.patch(
        f"/api/cases/{case['id']}",
        headers={"X-CSRF-Token": user["csrfToken"]},
        json={"revision": case["revision"], "document": next_document, "steps": steps},
    )


def save_title(client: TestClient, user: dict, case: dict, title: str):
    return client.patch(
        f"/api/cases/{case['id']}",
        headers={"X-CSRF-Token": user["csrfToken"]},
        json={"revision": case["revision"], "title": title},
    )


def merge_path(case: dict, annotation: dict) -> str:
    return f"/api/cases/{case['id']}/annotations/{annotation['id']}/merge"


def test_merge_uses_latest_revision_after_unrelated_edit_and_is_idempotent(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    seed_revisions(client, annotation, "旧轮改写", "最新有效改写")
    saved = _edit_before_merge(client, user, case)
    merged = client.post(merge_path(saved, annotation), headers={"X-CSRF-Token": user["csrfToken"]})
    _assert_merge_applied_latest(merged, saved)
    repeated = client.post(
        merge_path(merged.json()["case"], annotation),
        headers={"X-CSRF-Token": user["csrfToken"]},
    )
    assert repeated.status_code == 200
    assert repeated.json()["case"]["revision"] == merged.json()["case"]["revision"]


def test_merge_accepts_selected_artifact_and_expires_other_revision(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    artifact_ids = seed_linked_revisions(client, annotation, "旧轮改写", "最新有效改写")

    response = client.post(
        merge_path(case, annotation), headers={"X-CSRF-Token": user["csrfToken"]}
    )
    _assert_linked_merge_result(client, response, artifact_ids)


def test_merge_rejects_stale_baseline_and_expires_linked_artifact(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    artifact_ids = seed_linked_revisions(client, annotation, "过期基线改写")
    changed = save_title(client, user, case, "标题已更新")
    assert changed.status_code == 200

    response = client.post(
        merge_path(changed.json(), annotation), headers={"X-CSRF-Token": user["csrfToken"]}
    )

    assert response.status_code == 409
    current = client.get(f"/api/cases/{case['id']}").json()
    assert current["revision"] == 2 and current["document"] == document("目标正文")
    row = client.get(f"/api/cases/{case['id']}/annotations").json()[0]
    assert row["revisions"][0]["status"] == "expired"
    assert client.app.state.database.agent_artifacts.find_one({"id": artifact_ids[0]})["status"] == "expired"


def _assert_linked_merge_result(client: TestClient, response, artifact_ids: list[str]) -> None:
    assert response.status_code == 200
    result = response.json()
    assert result["annotation"]["status"] == "resolved"
    assert [row["status"] for row in result["annotation"]["revisions"]] == [
        "expired", "accepted",
    ]
    statuses = [client.app.state.database.agent_artifacts.find_one({"id": artifact_id})["status"]
                for artifact_id in artifact_ids]
    assert statuses == ["expired", "accepted"]


def _edit_before_merge(client: TestClient, user: dict, case: dict) -> dict:
    saved = save_document(
        client, user, case, document("前置目标正文"),
        [{"stepType": "replace", "from": paragraph_start(), "to": paragraph_start(),
          "slice": {"content": [{"type": "text", "text": "前置"}]}}],
    )
    assert saved.status_code == 200
    return saved.json()


def _assert_merge_applied_latest(merged, saved_case) -> None:
    assert merged.status_code == 200
    result = merged.json()
    assert result["annotation"]["status"] == "resolved"
    assert result["annotation"]["revisions"][-1]["status"] == "accepted"
    assert result["case"]["revision"] == saved_case["revision"] + 1
    assert "最新有效改写" in result["case"]["document"]["content"][1]["content"][0]["text"]


def test_direct_close_keeps_body_and_revision_history(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    seed_revisions(client, annotation, "不应写入正文")
    response = client.patch(
        f"/api/cases/{case['id']}/annotations/{annotation['id']}/status",
        headers={"X-CSRF-Token": user["csrfToken"]}, json={"status": "resolved"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    assert response.json()["revisions"][0]["status"] == "rejected"
    current = client.get(f"/api/cases/{case['id']}").json()
    assert current["revision"] == case["revision"]
    assert current["document"] == document("目标正文")


def test_merge_rejects_changed_target_without_body_write(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    seed_revisions(client, annotation, "不应写入正文")
    changed = save_document(
        client, user, case, document("改写后的目标"),
        [{"stepType": "replace", "from": paragraph_start(), "to": paragraph_start() + len("目标正文"),
          "slice": {"content": [{"type": "text", "text": "改写后的目标"}]}}],
    )
    assert changed.status_code == 200
    response = client.post(merge_path(changed.json(), annotation), headers={"X-CSRF-Token": user["csrfToken"]})
    assert response.status_code == 409
    current = client.get(f"/api/cases/{case['id']}").json()
    assert current["document"] == document("改写后的目标")
    row = client.get(f"/api/cases/{case['id']}/annotations").json()[0]
    assert row["anchorState"] == "changed"
    assert row["revisions"][0]["status"] == "expired"


def test_non_owner_cannot_merge_author_annotation(client: TestClient) -> None:
    owner = login(client, "user", "user123")
    case = create_case(client, owner, "目标正文")
    annotation = create_annotation(client, owner, case, "目标正文")
    seed_revisions(client, annotation, "越权改写")
    admin = login(client, "admin", "admin123")
    response = client.post(
        merge_path(case, annotation), headers={"X-CSRF-Token": admin["csrfToken"]}
    )
    assert response.status_code == 403


def _status(client: TestClient, case: dict, annotation: dict, user: dict, value: str):
    return client.patch(
        f"/api/cases/{case['id']}/annotations/{annotation['id']}/status",
        headers={"X-CSRF-Token": user["csrfToken"]}, json={"status": value},
    )


def _annotation_rows(client: TestClient, case: dict, user: dict) -> list[dict]:
    return client.get(
        f"/api/cases/{case['id']}/annotations",
        headers={"X-CSRF-Token": user["csrfToken"]},
    ).json()


def _ensure_second_teacher(client: TestClient) -> None:
    from app.modules.auth.passwords import hash_password

    client.app.state.database.users.update_one(
        {"id": "u-second-teacher"},
        {"$setOnInsert": {
            "id": "u-second-teacher", "username": "second", "name": "另一位教师",
            "role": "user", "status": "active", "must_change_password": False,
            "campus_verified": True, "token_version": 0,
            "password_hash": hash_password("second-pass"),
        }},
        upsert=True,
    )


def _private_annotation_requests(client: TestClient, case: dict, annotation: dict, user: dict):
    root = f"/api/cases/{case['id']}/annotations/{annotation['id']}"
    headers = {"X-CSRF-Token": user["csrfToken"]}
    return [
        client.get(f"/api/cases/{case['id']}/annotations", headers=headers),
        client.post(f"{root}/replies", headers=headers, json={"content": "越权回复"}),
        client.patch(root, headers=headers, json={"content": "越权修改"}),
        client.delete(root, headers=headers),
        client.patch(f"{root}/status", headers=headers, json={"status": "pending"}),
        client.post(f"{root}/merge", headers=headers),
    ]


def _assert_private_annotation_denied(
    client: TestClient, case: dict, annotation: dict, user: dict, list_status: int
) -> None:
    responses = _private_annotation_requests(client, case, annotation, user)
    assert responses[0].status_code == list_status
    assert all(response.status_code == 403 for response in responses[1:])
    assert all("请补充评价依据。" not in response.text for response in responses)


def test_private_annotation_all_public_entries_are_isolated(client: TestClient) -> None:
    author = login(client, "user", "user123")
    case = create_case(client, author, "目标正文")
    annotation = create_annotation(client, author, case, "目标正文")
    _ensure_second_teacher(client)
    _assert_private_annotation_denied(
        client, case, annotation, login(client, "admin", "admin123"), 200
    )
    _assert_private_annotation_denied(
        client, case, annotation, login(client, "second", "second-pass"), 403
    )
    author = login(client, "user", "user123")
    current = _annotation_rows(client, case, author)[0]
    assert current["status"] == "pending"
    assert current["content"] == "请补充评价依据。"
    assert current["replies"] == []


def test_admin_cannot_reopen_private_annotation(client: TestClient) -> None:
    author = login(client, "user", "user123")
    case = create_case(client, author, "目标正文")
    annotation = create_annotation(client, author, case, "目标正文")
    assert _status(client, case, annotation, author, "resolved").status_code == 200
    admin = login(client, "admin", "admin123")
    assert _status(client, case, annotation, admin, "pending").status_code == 403
    author = login(client, "user", "user123")
    current = _annotation_rows(client, case, author)[0]
    assert current["status"] == "resolved"
    assert current["content"] == "请补充评价依据。"
