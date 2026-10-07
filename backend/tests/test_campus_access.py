from __future__ import annotations

import uuid

import pytest
from app.modules.auth.management_service import (
    AccountManagementError,
    AccountManagementService,
)
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
        "grantSource": None,
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
    assert user["campus_application_revision"] == 1
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


@pytest.mark.parametrize(
    "change", ["force_logout", "disable", "require_password_change"]
)
def test_application_rechecks_applicant_after_http_guard(
    client: TestClient, monkeypatch, change: str,
) -> None:
    username = f"issue360-stale-applicant-{uuid.uuid4().hex}"
    session, _password = _register_and_login(client, username)
    database = client.app.state.database
    admin = database.users.find_one({"username": "admin"})
    original_submit = AccountManagementService.submit_campus_application

    def invalidate_then_submit(service, user, applicant_name, student_number):
        if change == "force_logout":
            service.force_logout(admin, user["id"], "合成申请前撤销会话")
        elif change == "disable":
            service.change_status(admin, user["id"], "disabled", "合成申请前停用")
        else:
            database.users.update_one(
                {"id": user["id"]}, {"$set": {"must_change_password": True}}
            )
        return original_submit(service, user, applicant_name, student_number)

    monkeypatch.setattr(
        AccountManagementService, "submit_campus_application", invalidate_then_submit
    )
    response = client.post(
        "/api/auth/campus-access/applications",
        headers={"X-CSRF-Token": session["csrfToken"]},
        json={"applicantName": "合成过期申请人", "studentNumber": "SYN-360-STALE"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "当前账号会话已变化，请重新登录后重试"
    assert database.campus_access_applications.count_documents({
        "userId": session["user"]["id"],
    }) == 0
    rejected = database.account_management_operations.find_one({
        "action": "campus_access_application_submit",
        "actorId": session["user"]["id"],
        "result": "rejected",
    })
    assert rejected["detail"] == response.json()["detail"]


def test_application_rejects_session_changed_after_current_applicant_read(
    client: TestClient, monkeypatch,
) -> None:
    username = f"issue360-changing-applicant-{uuid.uuid4().hex}"
    session, _password = _register_and_login(client, username)
    database = client.app.state.database
    original = AccountManagementService._require_current_applicant

    def change_session_after_read(service, applicant, transaction):
        current = original(service, applicant, transaction)
        database.users.update_one(
            {"id": applicant["id"]}, {"$inc": {"token_version": 1}}
        )
        return current

    monkeypatch.setattr(
        AccountManagementService,
        "_require_current_applicant",
        change_session_after_read,
    )
    response = client.post(
        "/api/auth/campus-access/applications",
        headers={"X-CSRF-Token": session["csrfToken"]},
        json={"applicantName": "合成交错申请人", "studentNumber": "SYN-360-RACE"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "当前账号会话已变化，请重新登录后重试"
    assert database.campus_access_applications.count_documents({
        "userId": session["user"]["id"],
    }) == 0
    rejected = database.account_management_operations.find_one({
        "action": "campus_access_application_submit",
        "actorId": session["user"]["id"],
        "result": "rejected",
    })
    assert rejected["detail"] == response.json()["detail"]


def test_admin_can_revoke_legacy_grant_without_an_application_record(
    client: TestClient,
) -> None:
    database = client.app.state.database
    target = database.users.find_one({"username": "user"})
    database.users.update_one(
        {"id": target["id"]},
        {"$set": {
            "campus_verified": True,
            "campus_access_grant_source": "legacy",
        }},
    )
    admin = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    ).json()

    listed = client.get("/api/admin/campus-access-legacy-grants?q=user")
    assert listed.status_code == 200
    assert listed.json()["items"] == [{
        "userId": target["id"], "username": "user", "role": "user",
        "grantSource": "legacy",
    }]

    revoked = client.post(
        f"/api/admin/campus-access-users/{target['id']}/revoke-legacy",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={"reason": "合成旧系统资格复核撤销"},
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json() == {
        "userId": target["id"], "username": "user", "campusVerified": False,
        "grantSource": "legacy", "revokedAt": revoked.json()["revokedAt"],
    }
    stored = database.users.find_one({"id": target["id"]})
    assert stored["campus_verified"] is False
    assert stored["campus_access_grant_source"] == "legacy"
    assert stored["campus_access_revoked_at"] == revoked.json()["revokedAt"]
    assert database.campus_access_applications.count_documents({"userId": target["id"]}) == 0
    operation = database.account_management_operations.find_one({
        "action": "campus_access_legacy_revoke", "targetId": target["id"],
    })
    assert operation["reason"] == "合成旧系统资格复核撤销"
    assert "campusApplicationId" not in operation

    applicant = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    ).json()
    status = client.get("/api/auth/campus-access").json()
    assert status["campusVerified"] is False
    assert status["grantSource"] == "legacy"
    assert status["currentStatus"] == "revoked"
    pending = client.post(
        "/api/auth/campus-access/applications",
        headers={"X-CSRF-Token": applicant["csrfToken"]},
        json={"applicantName": "合成重新申请", "studentNumber": "SYN-360-LEGACY"},
    )
    assert pending.status_code == 201
    assert client.get("/api/auth/campus-access").json()["campusVerified"] is False
    assert database.users.find_one({"id": target["id"]})[
        "campus_access_grant_source"
    ] == "legacy"

    from app.core.database import initialize

    initialize(database)
    assert database.users.find_one({"id": target["id"]})[
        "campus_verified"
    ] is False


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


@pytest.mark.parametrize(
    ("operation", "actor_change"),
    [
        ("approve", "demote"),
        ("approve", "disable"),
        ("reject", "demote"),
        ("reject", "disable"),
        ("revoke", "demote"),
        ("revoke", "disable"),
        ("approve", "force_logout"),
        ("reject", "force_logout"),
        ("revoke", "force_logout"),
    ],
)
def test_campus_management_rechecks_actor_inside_transaction(
    client: TestClient, operation: str, actor_change: str
) -> None:
    applicant_username = f"issue360-stale-actor-{uuid.uuid4().hex}"
    applicant, _password = _register_and_login(client, applicant_username)
    submitted = client.post(
        "/api/auth/campus-access/applications",
        headers={"X-CSRF-Token": applicant["csrfToken"]},
        json={"applicantName": "合成申请人", "studentNumber": "SYN-360-STALE"},
    )
    assert submitted.status_code == 201
    application_id = submitted.json()["id"]

    actor_username = f"issue360-actor-{uuid.uuid4().hex}"
    actor_session, _actor_password = _register_and_login(client, actor_username)
    database = client.app.state.database
    actor_id = actor_session["user"]["id"]
    database.users.update_one({"id": actor_id}, {"$set": {"role": "admin"}})
    stale_actor = database.users.find_one({"id": actor_id})

    supervisor_username = f"issue360-supervisor-{uuid.uuid4().hex}"
    supervisor_session, _supervisor_password = _register_and_login(
        client, supervisor_username
    )
    supervisor_id = supervisor_session["user"]["id"]
    database.users.update_one({"id": supervisor_id}, {"$set": {"role": "admin"}})
    supervisor = database.users.find_one({"id": supervisor_id})
    service = AccountManagementService(database)

    if operation == "revoke":
        service.decide_campus_application(
            supervisor, application_id, "approved", "合成初次批准"
        )
    if actor_change == "demote":
        service.change_role(supervisor, actor_id, "user", "合成撤销操作者角色")
    elif actor_change == "disable":
        service.change_status(supervisor, actor_id, "disabled", "合成停用操作者")
    else:
        service.force_logout(supervisor, actor_id, "合成强退资格操作员")

    with pytest.raises(AccountManagementError) as error:
        if operation == "revoke":
            service.revoke_campus_access(
                stale_actor, application_id, "合成过期操作者撤销"
            )
        else:
            decision = "approved" if operation == "approve" else "rejected"
            service.decide_campus_application(
                stale_actor, application_id, decision, "合成过期操作者决定"
            )

    assert error.value.status_code == 403
    applicant_login = client.post(
        "/api/auth/login", json={"username": applicant_username, "password": _password}
    )
    assert applicant_login.status_code == 200
    status = client.get("/api/auth/campus-access").json()
    application = status["applications"][0]
    assert application["status"] == ("approved" if operation == "revoke" else "pending")
    assert status["campusVerified"] is (operation == "revoke")
    assert "campus_access_revoked_at" not in database.users.find_one(
        {"id": applicant["user"]["id"]}
    )
    operation_name = {
        "approve": "campus_access_approve",
        "reject": "campus_access_reject",
        "revoke": "campus_access_revoke",
    }[operation]
    rejected = next(
        entry for entry in application["history"] if entry["action"] == operation_name
    )
    assert rejected["result"] == "rejected"
    assert rejected["detail"] == "管理员权限已变化，请重新登录后重试"


def test_legacy_campus_revoke_rejects_a_force_logged_out_admin(client: TestClient) -> None:
    database = client.app.state.database
    target = database.users.find_one({"id": "u-user-demo"})
    database.users.update_one(
        {"id": target["id"]},
        {"$set": {"campus_verified": True, "campus_access_grant_source": "legacy"}},
    )
    actor_session, _password = _register_and_login(
        client, f"issue360-legacy-actor-{uuid.uuid4().hex}"
    )
    actor_id = actor_session["user"]["id"]
    database.users.update_one({"id": actor_id}, {"$set": {"role": "admin"}})
    stale_actor = database.users.find_one({"id": actor_id})
    supervisor_session, _supervisor_password = _register_and_login(
        client, f"issue360-legacy-supervisor-{uuid.uuid4().hex}"
    )
    supervisor_id = supervisor_session["user"]["id"]
    database.users.update_one({"id": supervisor_id}, {"$set": {"role": "admin"}})
    supervisor = database.users.find_one({"id": supervisor_id})
    service = AccountManagementService(database)
    service.force_logout(supervisor, actor_id, "合成强退旧资格操作员")

    with pytest.raises(AccountManagementError) as error:
        service.revoke_legacy_campus_access(
            stale_actor, target["id"], "合成过期管理员撤销旧授权"
        )

    assert error.value.status_code == 403
    current_target = database.users.find_one({"id": target["id"]})
    assert current_target["campus_verified"] is True
    assert current_target["campus_access_grant_source"] == "legacy"
    rejected = database.account_management_operations.find_one(
        {"action": "campus_access_legacy_revoke", "targetId": target["id"]},
        sort=[("createdAt", -1)],
    )
    assert rejected["result"] == "rejected"
    assert rejected["detail"] == "管理员权限已变化，请重新登录后重试"
