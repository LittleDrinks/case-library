from __future__ import annotations

from fastapi.testclient import TestClient


def login(client: TestClient, username: str, password: str) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()


def lifecycle(client: TestClient, csrf: str, case_id: str, body: dict) -> dict:
    response = client.post(
        f"/api/cases/{case_id}/lifecycle",
        headers={"X-CSRF-Token": csrf},
        json=body,
    )
    assert response.status_code == 200
    return response.json()


def command(case: dict, name: str, **extra) -> dict:
    return {"command": name, "revision": case["revision"], **extra}


def reviewing_case(client: TestClient) -> tuple[dict, dict, dict]:
    author = login(client, "user", "user123")
    case = client.get("/api/cases/c-draft-1").json()
    submitted = lifecycle(client, author["csrfToken"], case["id"], command(case, "submit"))
    admin = login(client, "admin", "admin123")
    started = lifecycle(
        client,
        admin["csrfToken"],
        case["id"],
        command(submitted["case"], "start"),
    )
    return author, admin, started


def create_annotation(client: TestClient, admin: dict, case: dict) -> dict:
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


def assert_annotation_shape(annotation: dict, case: dict, admin: dict) -> None:
    assert annotation == {
        "id": annotation["id"],
        "caseId": case["id"],
        "versionId": case["submittedVersionId"],
        "quote": "供应中断周期不明",
        "section": "情境设定与前提假设",
        "content": "请明确对应的课程目标。",
        "source": "admin",
        "status": "pending",
        "replies": [],
        "createdBy": admin["user"]["id"],
        "createdAt": annotation["createdAt"],
    }


def test_admin_anchors_annotation_to_reviewed_version_and_author_reads_it(
    client: TestClient,
) -> None:
    author, admin, started = reviewing_case(client)
    case = started["case"]
    annotation = create_annotation(client, admin, case)
    assert_annotation_shape(annotation, case, admin)
    login(client, "user", "user123")
    rows = client.get(f"/api/cases/{case['id']}/annotations").json()
    assert rows == [annotation]


def author_resolves(
    client: TestClient, case: dict, annotation: dict
) -> tuple[dict, dict]:
    author = login(client, "user", "user123")
    root = f"/api/cases/{case['id']}/annotations/{annotation['id']}"
    replied = client.post(
        f"{root}/replies",
        headers={"X-CSRF-Token": author["csrfToken"]},
        json={"content": "已补充课程目标与教学活动的对应关系。"},
    )
    resolved = client.patch(
        f"{root}/status",
        headers={"X-CSRF-Token": author["csrfToken"]},
        json={"status": "resolved"},
    )
    assert replied.status_code == resolved.status_code == 200
    return author, resolved.json()


def admin_reopens(
    client: TestClient, case: dict, annotation: dict
) -> tuple[dict, dict]:
    admin = login(client, "admin", "admin123")
    root = f"/api/cases/{case['id']}/annotations/{annotation['id']}"
    followed_up = client.post(
        f"{root}/replies",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={"content": "对应关系还需要补充可观察的评价标准。"},
    )
    reopened = client.patch(
        f"{root}/status",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={"status": "pending"},
    )
    assert followed_up.status_code == reopened.status_code == 200
    return admin, reopened.json()


def test_author_resolves_thread_and_admin_reopens_it(client: TestClient) -> None:
    _author, admin, started = reviewing_case(client)
    case = started["case"]
    annotation = create_annotation(client, admin, case)
    author, _resolved = author_resolves(client, case, annotation)
    admin, reopened = admin_reopens(client, case, annotation)
    assert reopened["status"] == "pending"
    replies = reopened["replies"]
    assert [reply["content"] for reply in replies] == [
        "已补充课程目标与教学活动的对应关系。",
        "对应关系还需要补充可观察的评价标准。",
    ]
    assert [reply["createdBy"] for reply in replies] == [
        author["user"]["id"],
        admin["user"]["id"],
    ]


def test_annotation_anchor_must_exist_in_the_submitted_section(
    client: TestClient,
) -> None:
    _author, admin, started = reviewing_case(client)
    case = started["case"]
    response = client.post(
        f"/api/cases/{case['id']}/annotations",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={
            "quote": "这段文字不在冻结版本里",
            "section": "情境设定与前提假设",
            "content": "无效锚点不能成为审核意见。",
            "source": "admin",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "批注选区不属于待审版本小节"


def reject_command(case: dict) -> dict:
    return {
        "command": "reject",
        "revision": case["revision"],
        "submittedVersionId": case["submittedVersionId"],
        "reasonType": "教学目标不清晰",
        "summary": "请依据批注修改后重新提交。",
    }


def assert_rejected(returned: dict, case: dict, annotation: dict) -> None:
    assert returned["case"]["workflowStatus"] == "draft"
    assert returned["case"]["publicationStatus"] == "none"
    assert returned["case"]["submittedVersionId"] is None
    assert returned["event"]["action"] == "reject"
    assert returned["event"]["versionId"] == case["submittedVersionId"]
    assert returned["event"]["reasonType"] == "教学目标不清晰"
    assert returned["event"]["summary"] == "请依据批注修改后重新提交。"
    assert returned["event"]["annotationIds"] == [annotation["id"]]


def test_admin_cannot_reject_without_current_version_annotation(
    client: TestClient,
) -> None:
    author, admin, started = reviewing_case(client)
    case, command = started["case"], reject_command(started["case"])
    blocked = client.post(
        f"/api/cases/{case['id']}/lifecycle",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json=command,
    )
    annotation = create_annotation(client, admin, case)
    returned = lifecycle(client, admin["csrfToken"], case["id"], command)

    assert blocked.status_code == 409
    assert_rejected(returned, case, annotation)
    login(client, "user", "user123")
    assert client.get(f"/api/cases/{case['id']}/annotations").json() == [annotation]
    assert author["user"]["id"] == returned["case"]["ownerId"]


def publish_then_reopen(client: TestClient) -> tuple[dict, dict, dict, dict]:
    author, admin, first_review = reviewing_case(client)
    case = first_review["case"]
    approved = _approve_case(client, admin, case)
    hidden = _transition_case(client, admin, approved["case"], "hide")
    reopened = _transition_case(client, admin, hidden["case"], "reopen")
    return author, admin, approved, reopened


def _approve_case(client: TestClient, admin: dict, case: dict) -> dict:
    return _transition_case(
        client,
        admin,
        case,
        "approve",
        submittedVersionId=case["submittedVersionId"],
    )


def _transition_case(client: TestClient, admin: dict, case: dict, action: str, **extra) -> dict:
    return lifecycle(
        client,
        admin["csrfToken"],
        case["id"],
        command(case, action, **extra),
    )


def start_second_review(client: TestClient, case: dict) -> tuple[dict, dict]:
    author = login(client, "user", "user123")
    submitted = lifecycle(
        client, author["csrfToken"], case["id"], command(case, "submit")
    )
    admin = login(client, "admin", "admin123")
    started = _transition_case(client, admin, submitted["case"], "start")
    return admin, started


def supplement_command(case: dict) -> dict:
    return {
        "command": "supplement",
        "revision": case["revision"],
        "submittedVersionId": case["submittedVersionId"],
        "reasonType": "证据不足",
    }


def test_supplement_keeps_previous_publication_hidden(client: TestClient) -> None:
    _author, _admin, approved, reopened = publish_then_reopen(client)
    admin, started = start_second_review(client, reopened["case"])
    case = started["case"]
    annotation = create_annotation(client, admin, started["case"])
    command = supplement_command(case)
    wrong = client.post(
        f"/api/cases/{case['id']}/lifecycle",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={**command, "submittedVersionId": approved["version"]["id"]},
    )
    returned = lifecycle(client, admin["csrfToken"], case["id"], command)

    assert wrong.status_code == 409
    assert returned["case"]["workflowStatus"] == "draft"
    assert returned["case"]["publicationStatus"] == "hidden"
    assert returned["case"]["publishedVersionId"] == approved["version"]["id"]
    assert returned["event"]["action"] == "supplement"
    assert returned["event"]["annotationIds"] == [annotation["id"]]
