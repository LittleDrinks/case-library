from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Callable

from pymongo import ASCENDING, ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.core.ids import new_id
from app.modules.auth.passwords import PasswordPolicyError, hash_password, require_strong_password


class AccountManagementError(ValueError):
    def __init__(self, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class AccountManagementService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_accounts(self, query: str, page: int, page_size: int) -> dict:
        criteria = (
            {"username": {"$regex": re.escape(query), "$options": "i"}}
            if query
            else {}
        )
        total = self.database.users.count_documents(criteria)
        cursor = (
            self.database.users.find(
                criteria,
                {
                    "_id": 0,
                    "id": 1,
                    "username": 1,
                    "role": 1,
                    "must_change_password": 1,
                },
            )
            .sort("username", ASCENDING)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "items": [
                {
                    "id": account["id"],
                    "username": account["username"],
                    "role": account["role"],
                    "mustChangePassword": bool(
                        account.get("must_change_password", False)
                    ),
                }
                for account in cursor
            ],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def list_operations(self, page: int, page_size: int) -> dict:
        total = self.database.account_management_operations.count_documents({})
        items = list(
            self.database.account_management_operations.find(
                {},
                {
                    "_id": 0,
                    "id": 1,
                    "actorId": 1,
                    "actorUsername": 1,
                    "targetId": 1,
                    "targetUsername": 1,
                    "action": 1,
                    "createdAt": 1,
                    "reason": 1,
                    "result": 1,
                    "detail": 1,
                },
            )
            .sort([("createdAt", -1), ("_id", -1)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return {"items": items, "total": total, "page": page, "pageSize": page_size}

    def open_account(
        self, actor: dict, username: str, temporary_password: str, reason: str
    ) -> dict:
        safe_reason = reason.strip()
        if temporary_password and temporary_password in safe_reason:
            error = AccountManagementError("操作理由不能包含临时密码", 422)
            self._record_rejection(
                actor,
                "account_open",
                "[操作理由已省略]",
                None,
                username,
                error,
            )
            raise error
        try:
            require_strong_password(temporary_password, "临时密码")
        except PasswordPolicyError as error:
            failure = AccountManagementError(str(error), 422)
            self._record_rejection(
                actor, "account_open", safe_reason, None, username, failure
            )
            raise failure from error

        now = datetime.now(UTC).isoformat()
        user = {
            "id": new_id("u"),
            "username": username,
            "name": username,
            "password_hash": hash_password(temporary_password),
            "role": "user",
            "status": "active",
            "must_change_password": True,
            "campus_verified": False,
            "token_version": 0,
            "createdAt": now,
            "updatedAt": now,
        }

        def create(transaction) -> dict:
            options = _session_options(transaction)
            self.database.users.insert_one(user, **options)
            self._append_operation(
                actor,
                "account_open",
                safe_reason,
                user["id"],
                username,
                "success",
                "普通账号已开户",
                transaction,
            )
            return user

        try:
            created = self._with_transaction(create)
        except DuplicateKeyError as error:
            failure = AccountManagementError("用户名已存在", 409)
            self._record_rejection(
                actor, "account_open", safe_reason, None, username, failure
            )
            raise failure from error
        return _account_view(created)

    def reset_temporary_password(
        self,
        actor: dict,
        target_id: str,
        temporary_password: str,
        reason: str,
    ) -> dict:
        safe_reason = reason.strip()
        if temporary_password and temporary_password in safe_reason:
            error = AccountManagementError("操作理由不能包含临时密码", 422)
            self._record_rejection(
                actor,
                "temporary_password_reset",
                "[操作理由已省略]",
                target_id,
                None,
                error,
            )
            raise error
        try:
            require_strong_password(temporary_password, "临时密码")
        except PasswordPolicyError as error:
            failure = AccountManagementError(str(error), 422)
            self._record_rejection(
                actor,
                "temporary_password_reset",
                safe_reason,
                target_id,
                None,
                failure,
            )
            raise failure from error

        password_hash = hash_password(temporary_password)

        def reset(transaction) -> dict:
            options = _session_options(transaction)
            self._acquire_admin_guard(transaction)
            target = self.database.users.find_one({"id": target_id}, **options)
            if not target:
                raise AccountManagementError("账号不存在", 404)
            if target.get("status") != "active":
                raise AccountManagementError("账号当前不可用", 409)
            if (
                target.get("role") == "admin"
                and not target.get("must_change_password", False)
            ):
                available_admins = self.database.users.count_documents(
                    {
                        "role": "admin",
                        "status": "active",
                        "must_change_password": False,
                    },
                    **options,
                )
                if available_admins <= 1:
                    raise AccountManagementError(
                        "不能将最后一个可用管理员设为临时密码状态", 409
                    )
            updated = self.database.users.find_one_and_update(
                {
                    "_id": target["_id"],
                    "token_version": target["token_version"],
                    "password_hash": target["password_hash"],
                },
                {
                    "$set": {
                        "password_hash": password_hash,
                        "must_change_password": True,
                        "updatedAt": datetime.now(UTC).isoformat(),
                    },
                    "$inc": {"token_version": 1},
                },
                return_document=ReturnDocument.AFTER,
                **options,
            )
            if not updated:
                raise AccountManagementError("账号已变化，请重试", 409)
            self.database.sessions.delete_many({"user_id": target_id}, **options)
            self._append_operation(
                actor,
                "temporary_password_reset",
                safe_reason,
                target_id,
                target["username"],
                "success",
                "临时密码已重置",
                transaction,
            )
            return updated

        try:
            updated = self._with_transaction(reset)
        except AccountManagementError as error:
            self._record_rejection(
                actor,
                "temporary_password_reset",
                safe_reason,
                target_id,
                None,
                error,
            )
            raise
        return _account_view(updated)

    def force_logout(self, actor: dict, target_id: str, reason: str) -> dict:
        safe_reason = reason.strip()

        def revoke(transaction) -> dict:
            options = _session_options(transaction)
            target = self.database.users.find_one({"id": target_id}, **options)
            if not target:
                raise AccountManagementError("账号不存在", 404)
            if target.get("status") != "active":
                raise AccountManagementError("账号当前不可用", 409)
            updated = self.database.users.find_one_and_update(
                {"_id": target["_id"], "token_version": target["token_version"]},
                {"$inc": {"token_version": 1}},
                return_document=ReturnDocument.AFTER,
                **options,
            )
            if not updated:
                raise AccountManagementError("账号已变化，请重试", 409)
            revoked = self.database.sessions.delete_many(
                {"user_id": target_id}, **options
            )
            self._append_operation(
                actor,
                "force_logout",
                safe_reason,
                target_id,
                target["username"],
                "success",
                "已撤销账号的现有会话",
                transaction,
            )
            return {
                "account": _account_view(updated),
                "revokedSessions": revoked.deleted_count,
            }

        try:
            return self._with_transaction(revoke)
        except AccountManagementError as error:
            self._record_rejection(
                actor,
                "force_logout",
                safe_reason,
                target_id,
                None,
                error,
            )
            raise

    def _acquire_admin_guard(self, transaction) -> None:
        result = self.database.account_management_guards.update_one(
            {"_id": "available-admins"},
            {"$inc": {"revision": 1}},
            **_session_options(transaction),
        )
        if result.matched_count != 1:
            raise RuntimeError("管理员并发保护记录未初始化")

    def _with_transaction(self, action: Callable) -> dict:
        with self.database.client.start_session() as session:
            return session.with_transaction(action)

    def _record_rejection(
        self,
        actor: dict,
        action: str,
        reason: str,
        target_id: str | None,
        target_username: str | None,
        error: AccountManagementError,
    ) -> None:
        if target_id and not target_username:
            target = self.database.users.find_one(
                {"id": target_id}, {"_id": 0, "username": 1}
            )
            target_username = target.get("username") if target else None
        self._append_operation(
            actor,
            action,
            reason,
            target_id,
            target_username,
            "rejected",
            error.detail,
            None,
        )

    def _append_operation(
        self,
        actor: dict,
        action: str,
        reason: str,
        target_id: str | None,
        target_username: str | None,
        result: str,
        detail: str,
        transaction,
    ) -> None:
        operation = {
            "id": new_id("op"),
            "actorId": actor["id"],
            "actorUsername": actor["username"],
            "targetId": target_id,
            "targetUsername": target_username,
            "action": action,
            "createdAt": datetime.now(UTC).isoformat(),
            "reason": reason,
            "result": result,
            "detail": detail,
        }
        self.database.account_management_operations.insert_one(
            operation, **_session_options(transaction)
        )


def _session_options(transaction) -> dict:
    return {"session": transaction} if transaction is not None else {}


def _account_view(user: dict) -> dict:
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "mustChangePassword": bool(user.get("must_change_password", False)),
    }
