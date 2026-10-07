from __future__ import annotations

import json
import os
import uuid
from http.cookiejar import CookieJar
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
        return error.code, json.loads(content) if content else None


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
        assert database.account_management_operations.count_documents({}) == (
            prior_operation_count + 8
        )
        assert database.account_management_operations.count_documents(
            {"campusApplicationId": {"$in": [first["id"], second["id"], third["id"]]}}
        ) == 8
    finally:
        client.close()
