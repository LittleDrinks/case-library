from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from threading import Barrier
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import pytest
from pymongo import MongoClient

BASE_URL = os.environ.get("CASE_LIBRARY_E2E_URL")
MONGODB_URI = os.environ.get("AUTH_QUERY_MONGODB_URI")
pytestmark = pytest.mark.e2e("CASE_LIBRARY_E2E_URL", "AUTH_QUERY_MONGODB_URI")


def _opener():
    return build_opener(HTTPCookieProcessor(CookieJar()))


def _request(opener, method: str, path: str, body=None, csrf: str = ""):
    payload = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    request = Request(f"{BASE_URL}{path}", payload, headers, method=method)
    try:
        with opener.open(request) as response:
            content = response.read()
            return response.status, json.loads(content) if content else None
    except HTTPError as error:
        content = error.read()
        if not content:
            return error.code, None
        try:
            return error.code, json.loads(content)
        except json.JSONDecodeError:
            return error.code, content.decode()


def _login(opener, username: str, password: str) -> dict:
    status, payload = _request(
        opener,
        "POST",
        "/api/auth/login",
        {"username": username, "password": password},
    )
    assert status == 200
    return payload


def _submit(opener, csrf: str, name: str, student_number: str):
    return _request(
        opener,
        "POST",
        "/api/auth/campus-access/applications",
        {"applicantName": name, "studentNumber": student_number},
        csrf,
    )


def _admin_action(admin, csrf: str, application_id: str, action: str, body: dict):
    return _request(
        admin,
        "POST",
        f"/api/admin/campus-access-applications/{application_id}/{action}",
        body,
        csrf,
    )


def _run_concurrently(first, second):
    start = Barrier(3)

    def request_after_barrier(request):
        start.wait(timeout=10)
        return request()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_result = executor.submit(request_after_barrier, first)
        second_result = executor.submit(request_after_barrier, second)
        start.wait(timeout=10)
        return first_result.result(timeout=30), second_result.result(timeout=30)


def test_real_http_and_mongodb_preserve_application_approval_revocation_history() -> None:
    username = f"issue360-http-{uuid.uuid4().hex}"
    password = f"Issue360-{uuid.uuid4().hex}!a"
    student_numbers = [f"SYN-360-{uuid.uuid4().hex[:12]}" for _ in range(3)]
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    database = client.get_default_database()
    prior_operation_count = database.account_management_operations.count_documents({})

    try:
        anonymous = _opener()
        registered_status, registered = _request(
            anonymous,
            "POST",
            "/api/auth/register",
            {"username": username, "password": password},
        )
        assert registered_status == 201
        assert registered["campusVerified"] is False
        assert registered["name"] == username

        applicant = _opener()
        applicant_session = _login(applicant, username, password)
        applicant_id = applicant_session["user"]["id"]
        assert applicant_session["user"]["name"] == username
        assert applicant_session["user"]["campusVerified"] is False
        initial_status, initial = _request(applicant, "GET", "/api/auth/campus-access")
        assert initial_status == 200
        assert initial["currentStatus"] == "not_applied"

        first_status, first = _submit(
            applicant, applicant_session["csrfToken"], "合成姓名甲", student_numbers[0]
        )
        assert first_status == 201
        assert first["identitySource"] == "self_reported"
        assert first["status"] == "pending"
        assert _request(applicant, "GET", "/api/auth/campus-access")[1]["campusVerified"] is False

        admin = _opener()
        admin_session = _login(admin, "admin", "admin123")
        admin_id = admin_session["user"]["id"]
        queue_status, queue = _request(
            admin,
            "GET",
            f"/api/admin/campus-access-applications?q={username}&status=pending",
        )
        assert queue_status == 200
        assert [item["id"] for item in queue["items"]] == [first["id"]]
        rejected_status, rejected = _admin_action(
            admin,
            admin_session["csrfToken"],
            first["id"],
            "decision",
            {"decision": "rejected", "reason": "合成资料待补充"},
        )
        assert rejected_status == 200
        assert rejected["status"] == "rejected"
        assert rejected["history"][-1]["reason"] == "合成资料待补充"

        applicant_session = _login(applicant, username, password)
        status, rejected_status_view = _request(applicant, "GET", "/api/auth/campus-access")
        assert status == 200
        assert rejected_status_view["campusVerified"] is False
        assert rejected_status_view["applications"][0]["id"] == first["id"]

        second_status, second = _submit(
            applicant, applicant_session["csrfToken"], "合成姓名乙", student_numbers[1]
        )
        assert second_status == 201
        assert second["id"] != first["id"]
        assert _request(applicant, "GET", "/api/auth/campus-access")[1]["campusVerified"] is False

        admin_session = _login(admin, "admin", "admin123")
        approved_status, approved = _admin_action(
            admin,
            admin_session["csrfToken"],
            second["id"],
            "decision",
            {"decision": "approved", "reason": "合成身份核验通过"},
        )
        assert approved_status == 200
        assert approved["status"] == "approved"
        assert _request(applicant, "GET", "/api/auth/campus-access")[1]["campusVerified"] is True

        revoked_status, revoked = _admin_action(
            admin,
            admin_session["csrfToken"],
            second["id"],
            "revoke",
            {"reason": "合成资格复核后撤销"},
        )
        assert revoked_status == 200
        assert revoked["status"] == "revoked"
        assert _request(applicant, "GET", "/api/auth/campus-access")[1]["campusVerified"] is False
        assert database.users.find_one({"id": applicant_id})["campus_access_revoked_at"]

        applicant_session = _login(applicant, username, password)
        third_status, third = _submit(
            applicant, applicant_session["csrfToken"], "合成姓名丙", student_numbers[2]
        )
        assert third_status == 201
        assert _request(applicant, "GET", "/api/auth/campus-access")[1]["currentStatus"] == "pending"
        assert _request(applicant, "GET", "/api/auth/campus-access")[1]["campusVerified"] is False
        assert database.users.find_one({"id": applicant_id})["campus_access_revoked_at"]

        admin_session = _login(admin, "admin", "admin123")
        approved_again_status, approved_again = _admin_action(
            admin,
            admin_session["csrfToken"],
            third["id"],
            "decision",
            {"decision": "approved", "reason": "合成再次人工核验通过"},
        )
        assert approved_again_status == 200
        assert approved_again["status"] == "approved"

        final_status, final = _request(applicant, "GET", "/api/auth/campus-access")
        assert final_status == 200
        assert final["campusVerified"] is True
        assert final["currentStatus"] == "approved"
        assert [item["id"] for item in final["applications"]] == [
            third["id"],
            second["id"],
            first["id"],
        ]
        assert final["applications"][1]["status"] == "revoked"
        assert final["applications"][1]["history"][-1]["reason"] == "合成资格复核后撤销"
        assert final["applications"][2]["status"] == "rejected"
        assert final["applications"][2]["history"][-1]["reason"] == "合成资料待补充"
        assert "campus_access_revoked_at" not in database.users.find_one({"id": applicant_id})
        assert database.users.find_one({"id": applicant_id})["name"] == username
        assert database.campus_access_applications.count_documents({"userId": applicant_id}) == 3
        assert database.account_management_operations.count_documents({}) == prior_operation_count + 7
        operations = list(
            database.account_management_operations.find(
                {"campusApplicationId": {"$in": [first["id"], second["id"], third["id"]]}}
            )
        )
        assert len(operations) == 7
        assert all(operation["result"] == "success" for operation in operations)
        assert all(operation["targetId"] == applicant_id for operation in operations)
        assert all(
            operation["actorId"] == applicant_id
            if operation["action"] == "campus_access_application_submit"
            else operation["actorId"] == admin_id
            for operation in operations
        )
        assert {
            operation["reason"]
            for operation in operations
            if operation["action"] != "campus_access_application_submit"
        } == {
            "合成资料待补充",
            "合成身份核验通过",
            "合成资格复核后撤销",
            "合成再次人工核验通过",
        }
    finally:
        client.close()


@pytest.mark.parametrize(
    ("action", "decision", "actor_change"),
    [
        ("decision", "approved", "role"),
        ("decision", "approved", "status"),
        ("decision", "rejected", "role"),
        ("decision", "rejected", "status"),
        ("revoke", None, "role"),
        ("revoke", None, "status"),
    ],
)
def test_real_http_serializes_campus_action_with_admin_change(
    action: str, decision: str | None, actor_change: str
) -> None:
    applicant_username = f"issue360-race-applicant-{uuid.uuid4().hex}"
    applicant_password = f"Issue360-{uuid.uuid4().hex}!a"
    actor_username = f"issue360-race-admin-{uuid.uuid4().hex}"
    actor_password = f"Issue360-{uuid.uuid4().hex}!a"
    student_number = f"SYN-360-{uuid.uuid4().hex[:12]}"
    mongo = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    database = mongo.get_default_database()

    try:
        admin = _opener()
        admin_session = _login(admin, "admin", "admin123")
        applicant_registration, applicant_user = _request(
            _opener(),
            "POST",
            "/api/auth/register",
            {"username": applicant_username, "password": applicant_password},
        )
        assert applicant_registration == 201
        applicant = _opener()
        applicant_session = _login(applicant, applicant_username, applicant_password)
        submitted_status, application = _submit(
            applicant,
            applicant_session["csrfToken"],
            "合成并发申请人",
            student_number,
        )
        assert submitted_status == 201

        actor_registration_status, actor_user = _request(
            _opener(),
            "POST",
            "/api/auth/register",
            {"username": actor_username, "password": actor_password},
        )
        assert actor_registration_status == 201
        promoted_status, _promoted = _request(
            admin,
            "POST",
            f"/api/admin/accounts/{actor_user['id']}/role",
            {"role": "admin", "reason": "合成并发管理员初始化"},
            admin_session["csrfToken"],
        )
        assert promoted_status == 200
        actor = _opener()
        actor_session = _login(actor, actor_username, actor_password)
        actor_access_status, actor_access = _request(actor, "GET", "/api/auth/campus-access")
        assert actor_access_status == 200
        assert actor_access["campusVerified"] is False

        if action == "revoke":
            approved_status, approved = _admin_action(
                admin,
                admin_session["csrfToken"],
                application["id"],
                "decision",
                {"decision": "approved", "reason": "合成并发撤销准备"},
            )
            assert approved_status == 200
            assert approved["status"] == "approved"

        campus_body = (
            {"reason": "合成并发资格撤销"}
            if action == "revoke"
            else {"decision": decision, "reason": "合成并发申请决定"}
        )
        expected_action = (
            "campus_access_revoke"
            if action == "revoke"
            else f"campus_access_{'approve' if decision == 'approved' else 'reject'}"
        )
        actor_reason = "合成并发操作者角色变化" if actor_change == "role" else "合成并发操作者停用"

        def perform_campus_action():
            return _admin_action(
                actor,
                actor_session["csrfToken"],
                application["id"],
                action,
                campus_body,
            )

        def change_actor():
            suffix, body = (
                ("role", {"role": "user", "reason": actor_reason})
                if actor_change == "role"
                else ("status", {"status": "disabled", "reason": actor_reason})
            )
            return _request(
                admin,
                "POST",
                f"/api/admin/accounts/{actor_user['id']}/{suffix}",
                body,
                admin_session["csrfToken"],
            )

        (campus_status, campus_result), (change_status, changed_actor) = (
            _run_concurrently(perform_campus_action, change_actor)
        )
        assert change_status == 200
        assert changed_actor["role"] == ("user" if actor_change == "role" else "admin")
        assert changed_actor["status"] == ("active" if actor_change == "role" else "disabled")
        assert campus_status in {200, 401, 403}

        stored_application = database.campus_access_applications.find_one(
            {"id": application["id"]}
        )
        resulting_status = (
            "revoked"
            if action == "revoke" and campus_status == 200
            else "approved"
            if action == "revoke"
            else decision
            if campus_status == 200
            else "pending"
        )
        assert stored_application["status"] == resulting_status
        assert database.users.find_one({"id": applicant_user["id"]})[
            "campus_verified"
        ] is (resulting_status == "approved")
        current_status, current_access = _request(
            applicant, "GET", "/api/auth/campus-access"
        )
        assert current_status == 200
        assert current_access["campusVerified"] is (resulting_status == "approved")

        campus_operations = list(
            database.account_management_operations.find(
                {
                    "campusApplicationId": application["id"],
                    "action": expected_action,
                }
            )
        )
        if campus_status == 200:
            assert any(
                operation["actorId"] == actor_user["id"]
                and operation["result"] == "success"
                for operation in campus_operations
            )
        else:
            assert not any(operation["result"] == "success" for operation in campus_operations)
        manager_action = "account_role_change" if actor_change == "role" else "account_status_change"
        assert database.account_management_operations.find_one(
            {
                "action": manager_action,
                "targetId": actor_user["id"],
                "reason": actor_reason,
                "result": "success",
            }
        )
    finally:
        mongo.close()


def test_real_http_audit_insert_failure_rolls_back_campus_approval() -> None:
    username = f"issue360-audit-failure-{uuid.uuid4().hex}"
    password = f"Issue360-{uuid.uuid4().hex}!a"
    student_number = f"SYN-360-{uuid.uuid4().hex[:12]}"
    mongo = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    database = mongo.get_default_database()
    collection_name = "account_management_operations"
    collection_options = database.command(
        "listCollections", filter={"name": collection_name}
    )["cursor"]["firstBatch"][0].get("options", {})
    original_validator = collection_options.get("validator", {})
    original_validation_level = collection_options.get("validationLevel", "strict")
    original_validation_action = collection_options.get("validationAction", "error")

    try:
        registration_status, registered = _request(
            _opener(),
            "POST",
            "/api/auth/register",
            {"username": username, "password": password},
        )
        assert registration_status == 201
        applicant = _opener()
        applicant_session = _login(applicant, username, password)
        submitted_status, application = _submit(
            applicant,
            applicant_session["csrfToken"],
            "合成审计回滚申请人",
            student_number,
        )
        assert submitted_status == 201
        admin = _opener()
        admin_session = _login(admin, "admin", "admin123")
        prior_application_operations = database.account_management_operations.count_documents(
            {"campusApplicationId": application["id"]}
        )

        database.command(
            "collMod",
            collection_name,
            validator={"action": {"$ne": "campus_access_approve"}},
            validationLevel="strict",
            validationAction="error",
        )
        failed_status, failed_result = _admin_action(
            admin,
            admin_session["csrfToken"],
            application["id"],
            "decision",
            {"decision": "approved", "reason": "合成审计拒写回滚"},
        )
        assert failed_status == 500
        assert failed_result is not None
        assert database.campus_access_applications.find_one(
            {"id": application["id"]}
        )["status"] == "pending"
        assert database.users.find_one({"id": registered["id"]})[
            "campus_verified"
        ] is False
        assert database.account_management_operations.count_documents(
            {"campusApplicationId": application["id"]}
        ) == prior_application_operations
    finally:
        database.command(
            "collMod",
            collection_name,
            validator=original_validator,
            validationLevel=original_validation_level,
            validationAction=original_validation_action,
        )
        mongo.close()
