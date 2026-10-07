from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def _register_and_login(client: TestClient, username: str) -> tuple[dict, str]:
    password = f"Issue360-{uuid.uuid4().hex}!a"
    registered = client.post(
        "/api/auth/register", json={"username": username, "password": password}
    )
    assert registered.status_code == 201
    logged_in = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert logged_in.status_code == 200
    return logged_in.json(), password


def test_applicant_can_submit_and_query_self_reported_campus_application(
    client: TestClient,
) -> None:
    username = f"issue360-applicant-{uuid.uuid4().hex}"
    assert client.get("/api/auth/campus-access").status_code == 401
    session, _password = _register_and_login(client, username)

    initial = client.get("/api/auth/campus-access")
    assert initial.status_code == 200
    assert initial.json() == {
        "campusVerified": False,
        "currentStatus": "not_applied",
        "applications": [],
    }

    submitted = client.post(
        "/api/auth/campus-access/applications",
        headers={"X-CSRF-Token": session["csrfToken"]},
        json={"applicantName": "合成申请人", "studentNumber": "SYN-360-001"},
    )

    assert submitted.status_code == 201
    application = submitted.json()
    assert application["applicantName"] == "合成申请人"
    assert application["studentNumber"] == "SYN-360-001"
    assert application["identitySource"] == "self_reported"
    assert application["status"] == "pending"
    assert len(application["history"]) == 1
    assert application["history"][0]["action"] == "campus_access_application_submit"
    assert application["history"][0]["result"] == "success"

    duplicate = client.post(
        "/api/auth/campus-access/applications",
        headers={"X-CSRF-Token": session["csrfToken"]},
        json={"applicantName": "重复资料", "studentNumber": "SYN-360-002"},
    )
    assert duplicate.status_code == 409

    refreshed = client.get("/api/auth/campus-access")
    assert refreshed.status_code == 200
    assert refreshed.json()["currentStatus"] == "pending"
    assert refreshed.json()["applications"] == [application]
    user = client.app.state.database.users.find_one({"id": session["user"]["id"]})
    assert user["campus_verified"] is False
    assert user["name"] == username
    draft = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": session["csrfToken"]},
        json={
            "title": "未获校内资格仍可创作",
            "document": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "合成私人草稿"}],
                    }
                ],
            },
        },
    )
    assert draft.status_code == 200
    assert draft.json()["ownerId"] == session["user"]["id"]
    assert draft.json()["workflowStatus"] == "draft"


def test_application_can_be_rejected_reapplied_approved_revoked_and_approved_again(
    client: TestClient,
) -> None:
    applicant_username = f"issue360-cycle-{uuid.uuid4().hex}"
    applicant, applicant_password = _register_and_login(client, applicant_username)

    first = client.post(
        "/api/auth/campus-access/applications",
        headers={"X-CSRF-Token": applicant["csrfToken"]},
        json={"applicantName": "合成姓名甲", "studentNumber": "SYN-360-101"},
    )
    assert first.status_code == 201
    first_id = first.json()["id"]
    assert client.get("/api/admin/campus-access-applications").status_code == 403

    admin_username = f"issue360-admin-{uuid.uuid4().hex}"
    admin, admin_password = _register_and_login(client, admin_username)
    client.app.state.database.users.update_one(
        {"id": admin["user"]["id"]}, {"$set": {"role": "admin"}}
    )
    admin_login = client.post(
        "/api/auth/login",
        json={"username": admin_username, "password": admin_password},
    )
    assert admin_login.status_code == 200
    admin = admin_login.json()
    assert client.get("/api/auth/campus-access").json()["campusVerified"] is False

    queue = client.get("/api/admin/campus-access-applications")
    assert queue.status_code == 200
    assert [row["id"] for row in queue.json()["items"]] == [first_id]
    missing_csrf = client.post(
        f"/api/admin/campus-access-applications/{first_id}/decision",
        json={"decision": "rejected", "reason": "缺少 CSRF"},
    )
    assert missing_csrf.status_code == 403
    rejected = client.post(
        f"/api/admin/campus-access-applications/{first_id}/decision",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={"decision": "rejected", "reason": "合成资料不匹配"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["history"][-1]["reason"] == "合成资料不匹配"

    applicant_login = client.post(
        "/api/auth/login",
        json={"username": applicant_username, "password": applicant_password},
    )
    assert applicant_login.status_code == 200
    applicant = applicant_login.json()
    resubmitted = client.post(
        "/api/auth/campus-access/applications",
        headers={"X-CSRF-Token": applicant["csrfToken"]},
        json={"applicantName": "合成姓名乙", "studentNumber": "SYN-360-102"},
    )
    assert resubmitted.status_code == 201
    second_id = resubmitted.json()["id"]
    applicant_status = client.get("/api/auth/campus-access").json()
    assert applicant_status["campusVerified"] is False
    assert applicant_status["currentStatus"] == "pending"
    assert [row["id"] for row in applicant_status["applications"]] == [
        second_id,
        first_id,
    ]
    assert applicant_status["applications"][1]["status"] == "rejected"

    admin_login = client.post(
        "/api/auth/login",
        json={"username": admin_username, "password": admin_password},
    )
    admin = admin_login.json()
    approved = client.post(
        f"/api/admin/campus-access-applications/{second_id}/decision",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={"decision": "approved", "reason": "合成身份核验通过"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    repeated_decision = client.post(
        f"/api/admin/campus-access-applications/{second_id}/decision",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={"decision": "approved", "reason": "合成重复批准尝试"},
    )
    assert repeated_decision.status_code == 409
    assert repeated_decision.json()["detail"] == "申请已处理，不能重复决定"

    applicant_login = client.post(
        "/api/auth/login",
        json={"username": applicant_username, "password": applicant_password},
    )
    applicant = applicant_login.json()
    assert client.get("/api/auth/campus-access").json()["campusVerified"] is True

    admin_login = client.post(
        "/api/auth/login",
        json={"username": admin_username, "password": admin_password},
    )
    admin = admin_login.json()
    revoked = client.post(
        f"/api/admin/campus-access-applications/{second_id}/revoke",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={"reason": "合成资格复核后撤销"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert revoked.json()["history"][-1]["reason"] == "合成资格复核后撤销"

    applicant_login = client.post(
        "/api/auth/login",
        json={"username": applicant_username, "password": applicant_password},
    )
    applicant = applicant_login.json()
    after_revocation = client.get("/api/auth/campus-access").json()
    assert after_revocation["campusVerified"] is False
    assert after_revocation["currentStatus"] == "revoked"
    applicant_user = client.app.state.database.users.find_one(
        {"id": applicant["user"]["id"]}
    )
    revoked_at = applicant_user["campus_access_revoked_at"]
    third = client.post(
        "/api/auth/campus-access/applications",
        headers={"X-CSRF-Token": applicant["csrfToken"]},
        json={"applicantName": "合成姓名丙", "studentNumber": "SYN-360-103"},
    )
    assert third.status_code == 201
    third_id = third.json()["id"]
    assert client.get("/api/auth/campus-access").json()["campusVerified"] is False
    assert client.app.state.database.users.find_one(
        {"id": applicant["user"]["id"]}
    )["campus_access_revoked_at"] == revoked_at

    admin_login = client.post(
        "/api/auth/login",
        json={"username": admin_username, "password": admin_password},
    )
    admin = admin_login.json()
    approved_again = client.post(
        f"/api/admin/campus-access-applications/{third_id}/decision",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={"decision": "approved", "reason": "合成二次人工核验通过"},
    )
    assert approved_again.status_code == 200
    assert approved_again.json()["status"] == "approved"

    applicant_login = client.post(
        "/api/auth/login",
        json={"username": applicant_username, "password": applicant_password},
    )
    final_status = client.get("/api/auth/campus-access").json()
    assert final_status["campusVerified"] is True
    assert final_status["currentStatus"] == "approved"
    assert [row["id"] for row in final_status["applications"]] == [
        third_id,
        second_id,
        first_id,
    ]
    assert final_status["applications"][1]["status"] == "revoked"
    assert final_status["applications"][1]["history"][-2]["result"] == "rejected"
    assert final_status["applications"][1]["history"][-2]["reason"] == "合成重复批准尝试"
    assert final_status["applications"][0]["history"][-1]["reason"] == "合成二次人工核验通过"
    assert "password_hash" not in client.get("/api/auth/campus-access").text
    assert "campus_access_revoked_at" not in client.app.state.database.users.find_one(
        {"id": applicant["user"]["id"]}
    )
