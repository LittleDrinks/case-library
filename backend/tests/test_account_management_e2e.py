from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from http.cookiejar import CookieJar
from threading import Barrier
from typing import Any, Iterator
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import pytest
from pymongo import MongoClient
from pymongo.database import Database

BASE_URL = os.environ.get("CASE_LIBRARY_E2E_URL")
MONGODB_URI = os.environ.get("AUTH_QUERY_MONGODB_URI")
pytestmark = pytest.mark.e2e("CASE_LIBRARY_E2E_URL", "AUTH_QUERY_MONGODB_URI")

ADMIN_ACCOUNT_STATE_PROJECTION = {
    "_id": 0,
    "password_hash": 1,
    "role": 1,
    "status": 1,
    "must_change_password": 1,
    "token_version": 1,
}


@dataclass(frozen=True)
class _SyntheticAdmin:
    account_id: str
    username: str
    manager: Any
    session: dict[str, Any]


@dataclass(frozen=True)
class _AdminScenario:
    database: Database
    accounts: tuple[_SyntheticAdmin, ...]


@dataclass(frozen=True)
class _AccountSnapshots:
    users: dict[str, dict[str, Any]]
    session_counts: dict[str, int]


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
        if not content:
            return error.code, None
        try:
            return error.code, json.loads(content)
        except json.JSONDecodeError:
            return error.code, content.decode()


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


def _snapshot_original_admins(database: Database, fields: tuple[str, ...]):
    projection = {"_id": 0, "id": 1}
    projection.update({field: 1 for field in fields})
    return list(database.users.find({"role": "admin"}, projection))


def _create_synthetic_admin(
    database: Database,
    username_prefix: str,
    created_ids: list[str],
    campus_verified: bool,
) -> _SyntheticAdmin:
    manager = _opener()
    username = f"{username_prefix}-{uuid.uuid4().hex}"
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
    grant = {"role": "admin"}
    if campus_verified:
        grant["campus_verified"] = True
    database.users.update_one({"id": account_id}, {"$set": grant})
    return _SyntheticAdmin(
        account_id=account_id,
        username=username,
        manager=manager,
        session=_login(manager, username, password),
    )


def _cleanup_synthetic_admins(
    database: Database,
    created_ids: list[str],
    original_admins: list[dict[str, Any]],
    restore_fields: tuple[str, ...],
) -> None:
    if created_ids:
        database.users.delete_many({"id": {"$in": created_ids}})
        database.sessions.delete_many({"user_id": {"$in": created_ids}})
        database.account_management_operations.delete_many(
            {
                "$or": [
                    {"actorId": {"$in": created_ids}},
                    {"targetId": {"$in": created_ids}},
                ]
            }
        )
    for account in original_admins:
        original_state = {
            field: account[field] for field in restore_fields if field in account
        }
        database.users.update_one({"id": account["id"]}, {"$set": original_state})


@contextmanager
def _synthetic_admin_scenario(
    database: Database,
    account_count: int,
    username_prefix: str,
    *,
    campus_verified: bool = False,
    restore_fields: tuple[str, ...] = ("role",),
) -> Iterator[_AdminScenario]:
    original_admins = _snapshot_original_admins(database, restore_fields)
    created_ids: list[str] = []
    try:
        database.users.update_many({"role": "admin"}, {"$set": {"role": "user"}})
        accounts = tuple(
            _create_synthetic_admin(
                database, username_prefix, created_ids, campus_verified
            )
            for _ in range(account_count)
        )
        yield _AdminScenario(database=database, accounts=accounts)
    finally:
        _cleanup_synthetic_admins(
            database, created_ids, original_admins, restore_fields
        )


def _snapshot_admin_accounts(scenario: _AdminScenario) -> _AccountSnapshots:
    database = scenario.database
    return _AccountSnapshots(
        users={
            account.account_id: database.users.find_one(
                {"id": account.account_id}, ADMIN_ACCOUNT_STATE_PROJECTION
            )
            for account in scenario.accounts
        },
        session_counts={
            account.account_id: database.sessions.count_documents(
                {"user_id": account.account_id}
            )
            for account in scenario.accounts
        },
    )


def _assert_account_unchanged(
    scenario: _AdminScenario,
    snapshots: _AccountSnapshots,
    account: _SyntheticAdmin,
) -> None:
    state = scenario.database.users.find_one(
        {"id": account.account_id}, ADMIN_ACCOUNT_STATE_PROJECTION
    )
    if state != snapshots.users[account.account_id]:
        raise AssertionError("并发拒绝改动了目标账号")
    session_count = scenario.database.sessions.count_documents(
        {"user_id": account.account_id}
    )
    if session_count != snapshots.session_counts[account.account_id]:
        raise AssertionError("并发拒绝撤销了目标账号会话")


def _admin_change_after_barrier(
    barrier: Barrier,
    manager,
    csrf: str,
    target_id: str,
    path: str,
    body: dict[str, str],
) -> int:
    barrier.wait()
    return _request(manager, "POST", path.format(target_id=target_id), body, csrf)[0]


def _account_management_operations(manager) -> list[dict[str, Any]]:
    status, _ = _request(manager, "GET", "/api/admin/accounts")
    _expect_status(status, 200)
    status, operations = _request(manager, "GET", "/api/admin/account-operations")
    _expect_status(status, 200)
    return operations["items"]


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
        "status",
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


def test_failed_audit_insert_rolls_back_status_session_and_result() -> None:
    mongo = MongoClient(MONGODB_URI)
    database = mongo.get_default_database()
    collection_name = "account_management_operations"
    account_id = None
    validator_installed = False
    collection_options = {}
    try:
        admin, admin_session = _admin_session()
        account_id, username, temporary_password = _created_account(
            admin, admin_session["csrfToken"]
        )
        target = _opener()
        _login(target, username, temporary_password)
        marker = f"合成审计写入失败验收 {uuid.uuid4().hex}"
        collection_options = next(
            database.list_collections(filter={"name": collection_name})
        ).get("options", {})
        account_projection = {
            "_id": 0,
            "status": 1,
            "role": 1,
            "must_change_password": 1,
            "token_version": 1,
            "password_hash": 1,
        }
        original_state = database.users.find_one({"id": account_id}, account_projection)
        original_sessions = database.sessions.count_documents({"user_id": account_id})
        original_status_operations = (
            database.account_management_operations.count_documents(
                {"targetId": account_id, "action": "account_status_change"}
            )
        )
        try:
            database.command(
                "collMod",
                collection_name,
                validator={
                    "$or": [
                        {"reason": {"$ne": marker}},
                        {"auditFailureProbe": {"$exists": True}},
                    ]
                },
                validationLevel="strict",
                validationAction="error",
            )
            validator_installed = True
            status, failure = _request(
                admin,
                "POST",
                f"/api/admin/accounts/{account_id}/status",
                {"status": "disabled", "reason": marker},
                admin_session["csrfToken"],
            )
        finally:
            if validator_installed:
                database.command(
                    "collMod",
                    collection_name,
                    validator=collection_options.get("validator", {}),
                    validationLevel=collection_options.get("validationLevel", "strict"),
                    validationAction=collection_options.get(
                        "validationAction", "error"
                    ),
                )
                validator_installed = False

        _expect_status(status, 500)
        if not isinstance(failure, str) or not failure.strip():
            raise AssertionError("审计失败响应正文未保留")
        _expect_redacted(failure, (temporary_password,), "审计失败响应包含临时密码")
        unchanged_state = database.users.find_one(
            {"id": account_id}, account_projection
        )
        if unchanged_state != original_state:
            raise AssertionError("审计写入失败后账号状态未回滚")
        if (
            database.sessions.count_documents({"user_id": account_id})
            != original_sessions
        ):
            raise AssertionError("审计写入失败后账号会话被撤销")
        _expect_status(_request(target, "GET", "/api/auth/session")[0], 200)
        status, login_payload = _request(
            _opener(),
            "POST",
            "/api/auth/login",
            {"username": username, "password": temporary_password},
        )
        _expect_status(status, 200)
        _expect_redacted(login_payload, (temporary_password,), "登录响应包含临时密码")
        status, operations = _request(admin, "GET", "/api/admin/account-operations")
        _expect_status(status, 200)
        if any(
            operation["targetId"] == account_id
            and operation["action"] == "account_status_change"
            and operation["reason"] == marker
            for operation in operations["items"]
        ):
            raise AssertionError("审计写入失败后仍保存了账号状态操作")
        if (
            database.account_management_operations.count_documents(
                {"targetId": account_id, "action": "account_status_change"}
            )
            != original_status_operations
        ):
            raise AssertionError("审计写入失败后操作记录数量发生变化")
    finally:
        if validator_installed:
            database.command(
                "collMod",
                collection_name,
                validator=collection_options.get("validator", {}),
                validationLevel=collection_options.get("validationLevel", "strict"),
                validationAction=collection_options.get("validationAction", "error"),
            )
        if account_id:
            database.users.delete_one({"id": account_id})
            database.sessions.delete_many({"user_id": account_id})
            database.account_management_operations.delete_many({"targetId": account_id})
        mongo.close()


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


def _run_concurrent_password_resets(scenario: _AdminScenario) -> list[int]:
    barrier = Barrier(2)
    requests = ((0, 1, _password()), (1, 0, _password()))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = tuple(
            pool.submit(
                _admin_change_after_barrier,
                barrier,
                scenario.accounts[actor_index].manager,
                scenario.accounts[actor_index].session["csrfToken"],
                scenario.accounts[target_index].account_id,
                "/api/admin/accounts/{target_id}/temporary-password",
                {
                    "temporaryPassword": password,
                    "reason": "并发最后管理员 E2E",
                },
            )
            for actor_index, target_index, password in requests
        )
        return [future.result() for future in futures]


def _assert_last_admin_reset_statuses(statuses: list[int]) -> int:
    if statuses.count(200) != 1 or any(
        status not in (200, 401, 403) for status in statuses
    ):
        raise AssertionError(f"并发临时密码操作未基于当前管理员状态授权：{statuses}")
    return statuses.index(next(status for status in statuses if status != 200))


def _only_available_admin_id(database: Database) -> str:
    available_filter = {
        "role": "admin",
        "status": "active",
        "must_change_password": False,
    }
    if database.users.count_documents(available_filter) != 1:
        raise AssertionError("并发操作后可用管理员数量不正确")
    return database.users.find_one(available_filter, {"_id": 0, "id": 1})["id"]


def _account_reset_operations(
    operations: list[dict[str, Any]], account_ids: set[str]
) -> list[dict[str, Any]]:
    return [
        operation
        for operation in operations
        if operation["action"] == "temporary_password_reset"
        and operation["targetId"] in account_ids
    ]


def _assert_successful_reset_audit(
    operations: list[dict[str, Any]], scenario: _AdminScenario
) -> None:
    successful = [
        operation for operation in operations if operation["result"] == "success"
    ]
    if len(successful) != 1:
        raise AssertionError("并发重置的成功结果没有与账号事务一致")
    successful_target_id = successful[0]["targetId"]
    expected_actor_id = next(
        account.account_id
        for account in scenario.accounts
        if account.account_id != successful_target_id
    )
    if successful[0]["actorId"] != expected_actor_id:
        raise AssertionError("临时密码成功记录的操作者不正确")


def _assert_rejected_reset_audit(
    operations: list[dict[str, Any]],
    scenario: _AdminScenario,
    statuses: list[int],
    losing_index: int,
) -> None:
    rejected = [
        operation for operation in operations if operation["result"] == "rejected"
    ]
    if statuses[losing_index] == 403:
        target = scenario.accounts[1 - losing_index]
        actor = scenario.accounts[losing_index]
        rejected_target = next(
            (
                operation
                for operation in rejected
                if operation["targetId"] == target.account_id
            ),
            None,
        )
        if (
            not rejected_target
            or rejected_target["actorId"] != actor.account_id
            or rejected_target["targetUsername"] != target.username
            or rejected_target["reason"] != "并发最后管理员 E2E"
            or not rejected_target["detail"]
        ):
            raise AssertionError("并发授权拒绝未记录操作者、对象、理由和结果")
    elif rejected:
        raise AssertionError("会话已失效的请求不应进入管理操作记录")


def _assert_last_admin_reset_audit(
    operations: list[dict[str, Any]],
    scenario: _AdminScenario,
    statuses: list[int],
    losing_index: int,
) -> None:
    account_ids = {account.account_id for account in scenario.accounts}
    reset_operations = _account_reset_operations(operations, account_ids)
    _assert_successful_reset_audit(reset_operations, scenario)
    _assert_rejected_reset_audit(reset_operations, scenario, statuses, losing_index)


def _run_mixed_admin_removals(scenario: _AdminScenario) -> list[int]:
    barrier = Barrier(3)
    requests = (
        (
            0,
            1,
            "/api/admin/accounts/{target_id}/status",
            {"status": "disabled", "reason": "并发停用管理员 E2E"},
        ),
        (
            1,
            2,
            "/api/admin/accounts/{target_id}/role",
            {"role": "user", "reason": "并发降级管理员 E2E"},
        ),
        (
            2,
            0,
            "/api/admin/accounts/{target_id}/temporary-password",
            {
                "temporaryPassword": _password(),
                "reason": "并发重置管理员 E2E",
            },
        ),
    )
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = tuple(
            pool.submit(
                _admin_change_after_barrier,
                barrier,
                scenario.accounts[actor_index].manager,
                scenario.accounts[actor_index].session["csrfToken"],
                scenario.accounts[target_index].account_id,
                path,
                body,
            )
            for actor_index, target_index, path, body in requests
        )
        return [future.result() for future in futures]


def _assert_mixed_action_result(
    scenario: _AdminScenario,
    snapshots: _AccountSnapshots,
    account: _SyntheticAdmin,
    status: int,
    action: str,
) -> None:
    if status != 200:
        _assert_account_unchanged(scenario, snapshots, account)
        return
    state = scenario.database.users.find_one(
        {"id": account.account_id}, ADMIN_ACCOUNT_STATE_PROJECTION
    )
    session_count = scenario.database.sessions.count_documents(
        {"user_id": account.account_id}
    )
    original = snapshots.users[account.account_id]
    if action == "disable":
        if state["status"] != "disabled" or session_count != 0:
            raise AssertionError("并发停用没有提交状态并撤销会话")
    elif action == "demote":
        if (
            state["role"] != "user"
            or session_count != snapshots.session_counts[account.account_id]
        ):
            raise AssertionError("并发降级没有即时变更角色或意外撤销会话")
    elif action == "reset":
        if (
            state["password_hash"] == original["password_hash"]
            or state["must_change_password"] is not True
            or state["token_version"] != original["token_version"] + 1
            or session_count != 0
        ):
            raise AssertionError("并发密码重置没有提交密码版本并撤销会话")


def _assert_mixed_action_results(
    scenario: _AdminScenario,
    snapshots: _AccountSnapshots,
    statuses: list[int],
) -> None:
    actions = (
        (scenario.accounts[1], "disable"),
        (scenario.accounts[2], "demote"),
        (scenario.accounts[0], "reset"),
    )
    for status, (account, action) in zip(statuses, actions, strict=True):
        _assert_mixed_action_result(scenario, snapshots, account, status, action)


def _assert_mixed_statuses(statuses: list[int]) -> None:
    if statuses.count(200) != 2 or any(
        status not in (200, 401, 403, 409) for status in statuses
    ):
        raise AssertionError("混合并发管理员变更没有按持久化状态串行授权")


def _only_available_mixed_admin(scenario: _AdminScenario) -> dict[str, Any]:
    available = list(
        scenario.database.users.find(
            {"role": "admin", "status": "active", "must_change_password": False},
            {"_id": 0, "id": 1, "campus_verified": 1},
        )
    )
    account_ids = {account.account_id for account in scenario.accounts}
    if len(available) != 1 or available[0]["id"] not in account_ids:
        raise AssertionError("混合并发操作没有保留唯一可用管理员")
    if available[0].get("campus_verified") is not True:
        raise AssertionError("角色或状态变化修改了校内资格")
    return available[0]


def _assert_mixed_admin_audit(
    operations: list[dict[str, Any]],
    scenario: _AdminScenario,
    successful_count: int,
) -> None:
    account_ids = {account.account_id for account in scenario.accounts}
    actions = {
        "account_status_change",
        "account_role_change",
        "temporary_password_reset",
    }
    successful = [
        operation
        for operation in operations
        if operation["targetId"] in account_ids
        and operation["result"] == "success"
        and operation["action"] in actions
    ]
    if len(successful) != successful_count:
        raise AssertionError("并发成功结果没有全部写入账号操作记录")
    reasons = {operation["reason"] for operation in successful}
    if len(reasons) != len(successful) or any(
        not operation["detail"] for operation in successful
    ):
        raise AssertionError("并发操作记录缺少理由或结果")


def test_concurrent_last_available_admin_password_reset_preserves_management_access() -> (
    None
):
    with MongoClient(MONGODB_URI) as mongo:
        database = mongo.get_default_database()
        with _synthetic_admin_scenario(database, 2, "issue357-last-admin") as scenario:
            snapshots = _snapshot_admin_accounts(scenario)
            statuses = _run_concurrent_password_resets(scenario)
            losing_index = _assert_last_admin_reset_statuses(statuses)
            losing_target = scenario.accounts[1 - losing_index]
            _assert_account_unchanged(scenario, snapshots, losing_target)
            remaining_id = _only_available_admin_id(database)
            if remaining_id != losing_target.account_id:
                raise AssertionError("并发密码重置未保留仍可授权的管理员")
            remaining_admin = next(
                account
                for account in scenario.accounts
                if account.account_id == remaining_id
            )
            operations = _account_management_operations(remaining_admin.manager)
            _assert_last_admin_reset_audit(operations, scenario, statuses, losing_index)


def test_mixed_concurrent_admin_removal_preserves_one_real_management_session() -> None:
    with MongoClient(MONGODB_URI) as mongo:
        database = mongo.get_default_database()
        with _synthetic_admin_scenario(
            database,
            3,
            "issue359-mixed-admin",
            campus_verified=True,
            restore_fields=("role", "status", "must_change_password"),
        ) as scenario:
            snapshots = _snapshot_admin_accounts(scenario)
            statuses = _run_mixed_admin_removals(scenario)
            _assert_mixed_action_results(scenario, snapshots, statuses)
            _assert_mixed_statuses(statuses)
            remaining = _only_available_mixed_admin(scenario)
            remaining_admin = next(
                account
                for account in scenario.accounts
                if account.account_id == remaining["id"]
            )
            operations = _account_management_operations(remaining_admin.manager)
            _assert_mixed_admin_audit(operations, scenario, statuses.count(200))
