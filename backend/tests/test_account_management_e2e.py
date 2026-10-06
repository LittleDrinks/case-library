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


def _password() -> str:
    return f"Issue357-{uuid.uuid4().hex}!a"


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


def _expect_status(actual: int, expected: int) -> None:
    if actual != expected:
        raise AssertionError("公共 HTTP 请求状态不符合预期")


def _login(opener, username: str, password: str):
    status, payload = _request(
        opener,
        "POST",
        "/api/auth/login",
        {"username": username, "password": password},
    )
    _expect_status(status, 200)
    return payload


def _open_account(admin, csrf: str, username: str, password: str):
    return _request(
        admin,
        "POST",
        "/api/admin/accounts",
        {
            "username": username,
            "temporaryPassword": password,
            "reason": "合成账号管理 E2E",
        },
        csrf,
    )


def _expect_redacted(payload, secrets: tuple[str, ...], message: str) -> None:
    serialized = json.dumps(payload)
    for secret in secrets:
        if secret and secret in serialized:
            raise AssertionError(message)
    if "password_hash" in serialized:
        raise AssertionError(message)


def _admin_session():
    admin = _opener()
    return admin, _login(admin, "admin", "admin123")


def _registered_user(anonymous) -> tuple[str, str]:
    username = f"issue357-user-{uuid.uuid4().hex}"
    password = _password()
    status, registered = _request(
        anonymous,
        "POST",
        "/api/auth/register",
        {"username": username, "password": password},
    )
    _expect_status(status, 201)
    _expect_redacted(registered, (password,), "注册响应包含凭据")
    return username, password


def _created_account(admin, csrf: str) -> tuple[str, str, str]:
    username = f"issue357-managed-{uuid.uuid4().hex}"
    password = _password()
    status, opened = _open_account(admin, csrf, username, password)
    _expect_status(status, 201)
    _expect_redacted(opened, (password,), "开户响应包含凭据")
    return opened["id"], username, password


def _change_temporary_password(
    account_id: str, username: str, temporary_password: str, new_password: str
) -> tuple[object, object]:
    current_session = _opener()
    old_login = _login(current_session, username, temporary_password)
    _expect_status(_request(current_session, "GET", "/api/cases?scope=mine")[0], 403)
    concurrent_session = _opener()
    _login(concurrent_session, username, temporary_password)
    status, changed = _request(
        current_session,
        "POST",
        "/api/auth/change-password",
        {"currentPassword": temporary_password, "newPassword": new_password},
        old_login["csrfToken"],
    )
    _expect_status(status, 204)
    if changed is not None:
        raise AssertionError("改密响应不应返回认证会话")
    _expect_status(_request(current_session, "GET", "/api/auth/session")[0], 401)
    _expect_status(_request(concurrent_session, "GET", "/api/auth/session")[0], 401)
    status, _old_password_login = _request(
        _opener(),
        "POST",
        "/api/auth/login",
        {"username": username, "password": temporary_password},
    )
    _expect_status(status, 401)
    current_session = _opener()
    new_login = _login(current_session, username, new_password)
    if new_login["user"]["id"] != account_id or new_login["user"]["mustChangePassword"]:
        raise AssertionError("重新登录未保留账号身份或改密状态")
    _expect_status(_request(current_session, "GET", "/api/cases?scope=mine")[0], 200)
    second_session = _opener()
    _login(second_session, username, new_password)
    return current_session, second_session


def _reset_and_recover(
    admin,
    csrf: str,
    account_id: str,
    username: str,
    old_session,
    current_password: str,
    reset_password: str,
    recovered_password: str,
):
    status, reset = _request(
        admin,
        "POST",
        f"/api/admin/accounts/{account_id}/temporary-password",
        {"temporaryPassword": reset_password, "reason": "合成密码恢复 E2E"},
        csrf,
    )
    _expect_status(status, 200)
    if reset["id"] != account_id or reset["mustChangePassword"] is not True:
        raise AssertionError("重置未保留账号身份或首次改密状态")
    recovered = _opener()
    _expect_status(_request(old_session, "GET", "/api/auth/session")[0], 401)
    status, _stale = _request(
        recovered,
        "POST",
        "/api/auth/login",
        {"username": username, "password": current_password},
    )
    _expect_status(status, 401)
    first_login = _login(recovered, username, reset_password)
    status, _changed = _request(
        recovered,
        "POST",
        "/api/auth/change-password",
        {"currentPassword": reset_password, "newPassword": recovered_password},
        first_login["csrfToken"],
    )
    _expect_status(status, 204)
    _expect_status(_request(recovered, "GET", "/api/auth/session")[0], 401)
    recovered = _opener()
    recovered_login = _login(recovered, username, recovered_password)
    if first_login["user"]["id"] != account_id:
        raise AssertionError("临时密码登录改变了账号身份")
    if not first_login["user"]["mustChangePassword"]:
        raise AssertionError("临时密码登录未要求首次改密")
    if recovered_login["user"]["id"] != account_id:
        raise AssertionError("重新登录改变了账号身份")
    _expect_status(_request(recovered, "GET", "/api/cases?scope=mine")[0], 200)
    force_session = _opener()
    _login(force_session, username, recovered_password)
    return recovered, force_session


def _force_logout(admin, csrf: str, account_id: str, sessions: tuple) -> None:
    status, forced = _request(
        admin,
        "POST",
        f"/api/admin/accounts/{account_id}/force-logout",
        {"reason": "合成会话撤销 E2E"},
        csrf,
    )
    _expect_status(status, 200)
    if forced["account"]["id"] != account_id or forced["revokedSessions"] != len(sessions):
        raise AssertionError("强制退出未报告实际撤销会话")
    for opener in sessions:
        _expect_status(_request(opener, "GET", "/api/auth/session")[0], 401)


def _race_login_with_action(
    username: str,
    password: str,
    action_opener,
    action_path: str,
    action_body: dict,
    csrf: str,
):
    stale_login = _opener()
    start = Barrier(2)

    def login():
        start.wait()
        return _request(
            stale_login,
            "POST",
            "/api/auth/login",
            {"username": username, "password": password},
        )

    def action():
        start.wait()
        return _request(action_opener, "POST", action_path, action_body, csrf)

    with ThreadPoolExecutor(max_workers=2) as pool:
        login_future = pool.submit(login)
        action_future = pool.submit(action)
        login_result = login_future.result()
        action_result = action_future.result()
    return login_result, action_result, stale_login


def _verify_audit(
    admin,
    actor_id: str,
    account_id: str,
    username: str,
    secrets: tuple[str, ...],
) -> None:
    status, operations = _request(admin, "GET", "/api/admin/account-operations")
    _expect_status(status, 200)
    actions = [
        item
        for item in operations["items"]
        if item["targetId"] == account_id or item["targetUsername"] == username
    ]
    records = {(item["action"], item["result"]): item for item in actions}
    required = (
        ("account_open", "success", "合成账号管理 E2E"),
        ("temporary_password_reset", "success", "合成密码恢复 E2E"),
        ("force_logout", "success", "合成会话撤销 E2E"),
        ("account_open", "rejected", "合成账号管理 E2E"),
    )
    for action, result, reason in required:
        item = records.get((action, result))
        if not item:
            raise AssertionError("操作记录未持久化全部管理结果")
        if (
            item["actorId"] != actor_id
            or item["actorUsername"] != "admin"
            or item["targetUsername"] != username
            or item["reason"] != reason
            or not item["createdAt"]
            or not item["detail"]
        ):
            raise AssertionError("操作记录缺少操作者、对象、时间或理由")
        if action != "account_open" or result == "success":
            if item["targetId"] != account_id:
                raise AssertionError("操作记录没有稳定账号标识")
    if records[("account_open", "rejected")]["targetId"] is not None:
        raise AssertionError("开户拒绝记录的对象标识不正确")
    _expect_redacted(operations, secrets, "操作记录包含凭据")


def test_account_management_public_http_enforces_roles_csrf_and_redaction() -> None:
    anonymous = _opener()
    status, _ = _request(anonymous, "GET", "/api/admin/accounts")
    _expect_status(status, 401)

    admin, _admin_payload = _admin_session()
    csrf_password = _password()
    status, csrf_failure = _request(
        admin,
        "POST",
        "/api/admin/accounts",
        {
            "username": f"issue357-csrf-{uuid.uuid4().hex}",
            "temporaryPassword": csrf_password,
            "reason": "合成 CSRF 拒绝验收",
        },
    )
    _expect_status(status, 403)
    _expect_redacted(csrf_failure, (csrf_password,), "CSRF 拒绝响应包含凭据")

    regular_username, regular_password = _registered_user(anonymous)
    regular = _opener()
    regular_session = _login(regular, regular_username, regular_password)
    status, _ = _request(regular, "GET", "/api/admin/accounts")
    _expect_status(status, 403)
    status, _ = _request(regular, "GET", "/api/admin/account-operations")
    _expect_status(status, 403)
    status, regular_post = _request(
        regular,
        "POST",
        "/api/admin/accounts",
        {
            "username": f"issue357-forbidden-{uuid.uuid4().hex}",
            "temporaryPassword": _password(),
            "reason": "普通用户权限拒绝验收",
        },
        regular_session["csrfToken"],
    )
    _expect_status(status, 403)
    _expect_redacted(regular_post, (), "普通用户拒绝响应包含凭据")


def test_account_management_public_http_sessions_and_audit_persist_in_mongodb() -> None:
    admin, admin_session = _admin_session()
    csrf = admin_session["csrfToken"]
    account_id, username, temporary_password = _created_account(admin, csrf)
    status, listing = _request(
        admin, "GET", f"/api/admin/accounts?q={username.upper()}"
    )
    _expect_status(status, 200)
    if listing["total"] != 1 or listing["items"][0]["id"] != account_id:
        raise AssertionError("开户账号未从持久列表中查到")
    if set(listing["items"][0]) != {
        "id",
        "username",
        "role",
        "mustChangePassword",
    }:
        raise AssertionError("账号列表返回了额外资料")

    new_password = _password()
    current_session, _old_session = _change_temporary_password(
        account_id, username, temporary_password, new_password
    )
    reset_password = _password()
    recovered_password = _password()
    recovered, force_session = _reset_and_recover(
        admin,
        csrf,
        account_id,
        username,
        current_session,
        new_password,
        reset_password,
        recovered_password,
    )
    _force_logout(admin, csrf, account_id, (recovered, force_session))

    duplicate_password = _password()
    duplicate_status, duplicate = _open_account(
        admin, csrf, username, duplicate_password
    )
    _expect_status(duplicate_status, 409)
    _expect_redacted(duplicate, (duplicate_password,), "开户失败响应包含凭据")
    status, duplicate_listing = _request(
        admin, "GET", f"/api/admin/accounts?q={username}"
    )
    _expect_status(status, 200)
    if duplicate_listing["total"] != 1:
        raise AssertionError("重复开户错误地创建了第二个账号")
    _verify_audit(
        admin,
        admin_session["user"]["id"],
        account_id,
        username,
        (
            temporary_password,
            new_password,
            reset_password,
            recovered_password,
            duplicate_password,
        ),
    )


def test_public_http_rejects_invalid_account_fields_without_mutation() -> None:
    admin, admin_session = _admin_session()
    csrf = admin_session["csrfToken"]
    account_id, username, temporary_password = _created_account(admin, csrf)
    target_session = _opener()
    _login(target_session, username, temporary_password)
    operations_before = _request(
        admin, "GET", "/api/admin/account-operations"
    )[1]["total"]

    invalid_username = _request(
        admin,
        "POST",
        "/api/admin/accounts",
        {
            "username": "   ",
            "temporaryPassword": _password(),
            "reason": "合成空用户名校验",
        },
        csrf,
    )
    _expect_status(invalid_username[0], 422)

    invalid_open_username = f"issue357-invalid-open-{uuid.uuid4().hex}"
    invalid_open = _request(
        admin,
        "POST",
        "/api/admin/accounts",
        {
            "username": invalid_open_username,
            "temporaryPassword": _password(),
            "reason": "   ",
        },
        csrf,
    )
    _expect_status(invalid_open[0], 422)
    status, invalid_open_listing = _request(
        admin,
        "GET",
        f"/api/admin/accounts?q={invalid_open_username}",
    )
    _expect_status(status, 200)
    if invalid_open_listing["total"] != 0:
        raise AssertionError("空白理由开户仍创建了账号")

    long_reason_username = f"issue357-long-reason-{uuid.uuid4().hex}"
    invalid_long_reason = _request(
        admin,
        "POST",
        "/api/admin/accounts",
        {
            "username": long_reason_username,
            "temporaryPassword": _password(),
            "reason": "x" * 501,
        },
        csrf,
    )
    _expect_status(invalid_long_reason[0], 422)
    status, long_reason_listing = _request(
        admin,
        "GET",
        f"/api/admin/accounts?q={long_reason_username}",
    )
    _expect_status(status, 200)
    if long_reason_listing["total"] != 0:
        raise AssertionError("超长理由开户仍创建了账号")

    invalid_reset = _request(
        admin,
        "POST",
        f"/api/admin/accounts/{account_id}/temporary-password",
        {"temporaryPassword": _password(), "reason": "   "},
        csrf,
    )
    _expect_status(invalid_reset[0], 422)
    _expect_status(_request(target_session, "GET", "/api/auth/session")[0], 200)
    _expect_status(
        _request(_opener(), "POST", "/api/auth/login", {
            "username": username,
            "password": temporary_password,
        })[0],
        200,
    )

    invalid_logout = _request(
        admin,
        "POST",
        f"/api/admin/accounts/{account_id}/force-logout",
        {"reason": "   "},
        csrf,
    )
    _expect_status(invalid_logout[0], 422)
    _expect_status(_request(target_session, "GET", "/api/auth/session")[0], 200)
    for invalid_request in (
        invalid_username,
        invalid_open,
        invalid_long_reason,
        invalid_reset,
        invalid_logout,
    ):
        details = invalid_request[1].get("detail")
        if not isinstance(details, list) or any(
            not isinstance(issue, dict) or "input" in issue for issue in details
        ):
            raise AssertionError("字段校验响应格式错误或回显了输入")
    operations_after = _request(
        admin, "GET", "/api/admin/account-operations"
    )[1]["total"]
    if operations_after != operations_before:
        raise AssertionError("无效管理请求写入了操作记录")


def test_concurrent_old_password_logins_are_invalidated_by_reset_and_change() -> None:
    admin, admin_session = _admin_session()
    account_id, username, temporary_password = _created_account(
        admin, admin_session["csrfToken"]
    )
    reset_password = _password()
    login_result, reset_result, stale_reset_login = _race_login_with_action(
        username,
        temporary_password,
        admin,
        f"/api/admin/accounts/{account_id}/temporary-password",
        {
            "temporaryPassword": reset_password,
            "reason": "并发登录密码重置 E2E",
        },
        admin_session["csrfToken"],
    )
    _expect_status(reset_result[0], 200)
    if login_result[0] not in (200, 401):
        raise AssertionError("并发密码重置登录返回非预期状态")
    if reset_result[1]["mustChangePassword"] is not True:
        raise AssertionError("并发重置未保留首次改密状态")
    _expect_status(_request(stale_reset_login, "GET", "/api/auth/session")[0], 401)

    current = _opener()
    reset_login = _login(current, username, reset_password)
    changed_password = _password()
    login_result, change_result, stale_change_login = _race_login_with_action(
        username,
        reset_password,
        current,
        "/api/auth/change-password",
        {
            "currentPassword": reset_password,
            "newPassword": changed_password,
        },
        reset_login["csrfToken"],
    )
    _expect_status(change_result[0], 204)
    if login_result[0] not in (200, 401):
        raise AssertionError("并发改密登录返回非预期状态")
    if change_result[1] is not None:
        raise AssertionError("并发改密响应不应返回认证会话")
    _expect_status(_request(stale_change_login, "GET", "/api/auth/session")[0], 401)
    _expect_status(_request(current, "GET", "/api/auth/session")[0], 401)
    current = _opener()
    current_login = _login(current, username, changed_password)
    if current_login["user"]["id"] != account_id:
        raise AssertionError("改密后重新登录改变了账号身份")
    status, current_session = _request(current, "GET", "/api/auth/session")
    _expect_status(status, 200)
    if current_session["user"]["id"] != account_id:
        raise AssertionError("改密后的当前会话改变了账号身份")
    _expect_status(_request(current, "GET", "/api/cases?scope=mine")[0], 200)


def test_concurrent_last_available_admin_password_reset_preserves_management_access() -> None:
    mongo = MongoClient(MONGODB_URI)
    database = mongo.get_default_database()
    original_admins = list(
        database.users.find(
            {"role": "admin"}, {"_id": 0, "id": 1, "role": 1}
        )
    )
    created_ids: list[str] = []
    try:
        database.users.update_many({"role": "admin"}, {"$set": {"role": "user"}})
        manager_a = _opener()
        manager_b = _opener()
        ids = []
        usernames = []
        sessions = []
        for manager in (manager_a, manager_b):
            username = f"issue357-last-admin-{uuid.uuid4().hex}"
            password = _password()
            status, registered = _request(
                manager,
                "POST",
                "/api/auth/register",
                {"username": username, "password": password},
            )
            _expect_status(status, 201)
            account_id = registered["id"]
            created_ids.append(account_id)
            database.users.update_one(
                {"id": account_id}, {"$set": {"role": "admin"}}
            )
            sessions.append(_login(manager, username, password))
            ids.append(account_id)
            usernames.append(username)

        start = Barrier(2)

        def reset(manager, csrf: str, target_id: str, password: str):
            start.wait()
            return _request(
                manager,
                "POST",
                f"/api/admin/accounts/{target_id}/temporary-password",
                {"temporaryPassword": password, "reason": "并发最后管理员 E2E"},
                csrf,
            )[0]

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = (
                pool.submit(
                    reset, manager_a, sessions[0]["csrfToken"], ids[1], _password()
                ),
                pool.submit(
                    reset, manager_b, sessions[1]["csrfToken"], ids[0], _password()
                ),
            )
            statuses = sorted(future.result() for future in futures)

        if statuses != [200, 409]:
            raise AssertionError("并发临时密码操作未保护最后一个可用管理员")
        available_admins = database.users.count_documents(
            {"role": "admin", "status": "active", "must_change_password": False}
        )
        if available_admins != 1:
            raise AssertionError("并发操作后可用管理员数量不正确")
        remaining_id = database.users.find_one(
            {"role": "admin", "status": "active", "must_change_password": False},
            {"_id": 0, "id": 1},
        )["id"]
        remaining_manager = manager_a if remaining_id == ids[0] else manager_b
        status, _ = _request(remaining_manager, "GET", "/api/admin/accounts")
        _expect_status(status, 200)
        status, operations = _request(
            remaining_manager, "GET", "/api/admin/account-operations"
        )
        _expect_status(status, 200)
        rejected = next(
            (
                operation
                for operation in operations["items"]
                if operation["action"] == "temporary_password_reset"
                and operation["result"] == "rejected"
                and operation["targetId"] in ids
            ),
            None,
        )
        if not rejected:
            raise AssertionError("最后管理员拒绝结果未写入操作记录")
        target_index = ids.index(rejected["targetId"])
        if (
            rejected["targetUsername"] != usernames[target_index]
            or rejected["reason"] != "并发最后管理员 E2E"
            or not rejected["detail"]
        ):
            raise AssertionError("最后管理员拒绝记录没有正确标识操作对象")
    finally:
        if created_ids:
            database.users.delete_many({"id": {"$in": created_ids}})
            database.sessions.delete_many({"user_id": {"$in": created_ids}})
        for account in original_admins:
            database.users.update_one(
                {"id": account["id"]}, {"$set": {"role": account["role"]}}
            )
        mongo.close()
