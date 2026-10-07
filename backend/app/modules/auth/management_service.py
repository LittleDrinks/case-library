from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Callable

from pymongo import ASCENDING, ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.core.ids import new_id
from app.modules.auth.passwords import (
    PasswordPolicyError,
    hash_password,
    require_strong_password,
)

_TOKEN_VERSION_UNSET = object()


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
                    "status": 1,
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
                    "status": account.get("status", "active"),
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

    def campus_access_status(self, user: dict) -> dict:
        applications = list(
            self.database.campus_access_applications.find({"userId": user["id"]})
            .sort([("submittedAt", -1), ("_id", -1)])
        )
        views = [_campus_application_view(self.database, row) for row in applications]
        current_status = (
            views[0]["status"]
            if views
            else "revoked"
            if user.get("campus_access_revoked_at")
            else "not_applied"
        )
        return {
            "campusVerified": bool(user.get("campus_verified", False)),
            "grantSource": user.get("campus_access_grant_source"),
            "currentStatus": current_status,
            "applications": views,
        }

    def submit_campus_application(
        self, user: dict, applicant_name: str, student_number: str
    ) -> dict:
        safe_name = applicant_name.strip()
        safe_number = student_number.strip()
        now = datetime.now(UTC).isoformat()
        application = {
            "id": new_id("ca"),
            "userId": user["id"],
            "username": user["username"],
            "applicantName": safe_name,
            "studentNumber": safe_number,
            "identitySource": "self_reported",
            "status": "pending",
            "submittedAt": now,
        }

        def submit(transaction) -> dict:
            options = _session_options(transaction)
            self._acquire_admin_guard(transaction)
            current_user = self._require_current_applicant(user, transaction)
            if current_user.get("campus_verified", False):
                raise AccountManagementError("账号已有校内访问资格", 409)
            if self.database.campus_access_applications.find_one(
                {"userId": user["id"], "status": "pending"}, **options
            ):
                raise AccountManagementError("已有待审核的校内访问申请", 409)
            # 与强退、停用和改密写入同一账号文档，建立事务并发冲突点。
            serialized = self.database.users.update_one(
                {
                    "_id": current_user["_id"],
                    "status": "active",
                    "must_change_password": False,
                    "token_version": user.get("token_version"),
                },
                {"$inc": {"campus_application_revision": 1}},
                **options,
            )
            if serialized.matched_count != 1:
                raise AccountManagementError(
                    "当前账号会话已变化，请重新登录后重试", 401
                )
            self.database.campus_access_applications.insert_one(
                application, **options
            )
            self._append_operation(
                current_user,
                "campus_access_application_submit",
                "本人提交校内访问申请",
                user["id"],
                user["username"],
                "success",
                "校内访问申请已提交",
                transaction,
                campus_application_id=application["id"],
            )
            return application

        try:
            created = self._with_transaction(submit)
        except AccountManagementError as error:
            self._record_rejection(
                user,
                "campus_access_application_submit",
                "本人提交校内访问申请",
                user["id"],
                user["username"],
                error,
            )
            raise
        except DuplicateKeyError as error:
            failure = AccountManagementError("已有待审核的校内访问申请", 409)
            self._record_rejection(
                user,
                "campus_access_application_submit",
                "本人提交校内访问申请",
                user["id"],
                user["username"],
                failure,
            )
            raise failure from error
        return _campus_application_view(self.database, created)

    def list_campus_access_applications(
        self, query: str, status: str | None, page: int, page_size: int
    ) -> dict:
        criteria: dict = {}
        if status:
            criteria["status"] = status
        if query:
            expression = {"$regex": re.escape(query), "$options": "i"}
            criteria["$or"] = [
                {"username": expression},
                {"applicantName": expression},
                {"studentNumber": expression},
            ]
        total = self.database.campus_access_applications.count_documents(criteria)
        applications = list(
            self.database.campus_access_applications.find(criteria)
            .sort([("submittedAt", -1), ("_id", -1)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "items": [
                _campus_application_view(self.database, row, include_account=True)
                for row in applications
            ],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def list_legacy_campus_grants(self, query: str, page: int, page_size: int) -> dict:
        criteria: dict = {
            "campus_verified": True,
            "campus_access_grant_source": "legacy",
        }
        if query:
            expression = {"$regex": re.escape(query), "$options": "i"}
            criteria["$or"] = [
                {"username": expression},
                {"id": expression},
            ]
        total = self.database.users.count_documents(criteria)
        users = list(
            self.database.users.find(
                criteria, {"_id": 0, "id": 1, "username": 1, "role": 1}
            )
            .sort([("username", ASCENDING), ("id", ASCENDING)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "items": [
                {
                    "userId": user["id"],
                    "username": user["username"],
                    "role": user["role"],
                    "grantSource": "legacy",
                }
                for user in users
            ],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def revoke_legacy_campus_access(
        self, actor: dict, user_id: str, reason: str
    ) -> dict:
        def revoke(transaction) -> dict:
            options = _session_options(transaction)
            self._acquire_admin_guard(transaction)
            current_actor = self._require_current_admin(
                actor["id"], transaction, actor.get("token_version")
            )
            user = self.database.users.find_one(
                {
                    "id": user_id,
                    "campus_verified": True,
                    "campus_access_grant_source": "legacy",
                },
                **options,
            )
            if not user:
                raise AccountManagementError("旧系统校内资格不存在或已变化", 409)
            now = datetime.now(UTC).isoformat()
            changed = self.database.users.update_one(
                {
                    "_id": user["_id"],
                    "campus_verified": True,
                    "campus_access_grant_source": "legacy",
                },
                {"$set": {
                    "campus_verified": False,
                    "campus_access_revoked_at": now,
                }},
                **options,
            )
            if changed.matched_count != 1:
                raise AccountManagementError("旧系统校内资格已变化，不能重复撤销", 409)
            self._append_operation(
                current_actor,
                "campus_access_legacy_revoke",
                reason,
                user["id"],
                user["username"],
                "success",
                "旧系统校内访问资格已撤销",
                transaction,
            )
            return {
                "userId": user["id"],
                "username": user["username"],
                "campusVerified": False,
                "grantSource": "legacy",
                "revokedAt": now,
            }

        try:
            return self._with_transaction(revoke)
        except AccountManagementError as error:
            target = self.database.users.find_one(
                {"id": user_id}, {"_id": 0, "username": 1}
            )
            self._record_rejection(
                actor,
                "campus_access_legacy_revoke",
                reason,
                user_id,
                target.get("username") if target else None,
                error,
            )
            raise

    def decide_campus_application(
        self, actor: dict, application_id: str, decision: str, reason: str
    ) -> dict:
        action = "campus_access_approve" if decision == "approved" else "campus_access_reject"
        detail = "校内访问资格已批准" if decision == "approved" else "校内访问申请已拒绝"

        def decide(transaction) -> dict:
            options = _session_options(transaction)
            self._acquire_admin_guard(transaction)
            current_actor = self._require_current_admin(
                actor["id"], transaction, actor.get("token_version")
            )
            application = self.database.campus_access_applications.find_one(
                {"id": application_id}, **options
            )
            if not application:
                raise AccountManagementError("校内访问申请不存在", 404)
            if application["status"] != "pending":
                raise AccountManagementError("申请已处理，不能重复决定", 409)
            user = self.database.users.find_one(
                {"id": application["userId"], "status": "active"}, **options
            )
            if not user:
                raise AccountManagementError("申请人账号当前不可用", 409)
            updated = self.database.campus_access_applications.find_one_and_update(
                {"_id": application["_id"], "status": "pending"},
                {"$set": {"status": decision, "updatedAt": datetime.now(UTC).isoformat()}},
                return_document=ReturnDocument.AFTER,
                **options,
            )
            if not updated:
                raise AccountManagementError("申请已处理，不能重复决定", 409)
            if decision == "approved":
                self.database.users.update_one(
                    {"_id": user["_id"]},
                    {
                        "$set": {
                            "campus_verified": True,
                            "campus_access_granted_by_application_id": application_id,
                            "campus_access_grant_source": "application",
                        },
                        "$unset": {"campus_access_revoked_at": ""},
                    },
                    **options,
                )
            self._append_operation(
                current_actor,
                action,
                reason,
                user["id"],
                user["username"],
                "success",
                detail,
                transaction,
                campus_application_id=application_id,
            )
            return updated

        try:
            updated = self._with_transaction(decide)
        except AccountManagementError as error:
            application = self.database.campus_access_applications.find_one(
                {"id": application_id}
            )
            user = (
                self.database.users.find_one({"id": application["userId"]})
                if application
                else None
            )
            self._record_rejection(
                actor,
                action,
                reason,
                user["id"] if user else None,
                user["username"] if user else None,
                error,
                campus_application_id=application_id,
            )
            raise
        return _campus_application_view(self.database, updated, include_account=True)

    def revoke_campus_access(
        self, actor: dict, application_id: str, reason: str
    ) -> dict:
        def revoke(transaction) -> dict:
            options = _session_options(transaction)
            self._acquire_admin_guard(transaction)
            current_actor = self._require_current_admin(
                actor["id"], transaction, actor.get("token_version")
            )
            application = self.database.campus_access_applications.find_one(
                {"id": application_id}, **options
            )
            if not application:
                raise AccountManagementError("校内访问申请不存在", 404)
            if application["status"] != "approved":
                raise AccountManagementError("只有当前已批准的申请可以撤销", 409)
            user = self.database.users.find_one(
                {"id": application["userId"]}, **options
            )
            if not user or not user.get("campus_verified", False):
                raise AccountManagementError("账号当前没有校内访问资格", 409)
            now = datetime.now(UTC).isoformat()
            updated = self.database.campus_access_applications.find_one_and_update(
                {"_id": application["_id"], "status": "approved"},
                {"$set": {"status": "revoked", "updatedAt": now}},
                return_document=ReturnDocument.AFTER,
                **options,
            )
            if not updated:
                raise AccountManagementError("申请已变化，不能重复撤销", 409)
            changed = self.database.users.update_one(
                {"_id": user["_id"], "campus_verified": True},
                {
                    "$set": {
                        "campus_verified": False,
                        "campus_access_revoked_at": now,
                    },
                    "$unset": {"campus_access_granted_by_application_id": ""},
                },
                **options,
            )
            if changed.matched_count != 1:
                raise AccountManagementError("账号资格已变化，不能重复撤销", 409)
            self._append_operation(
                current_actor,
                "campus_access_revoke",
                reason,
                user["id"],
                user["username"],
                "success",
                "校内访问资格已撤销",
                transaction,
                campus_application_id=application_id,
            )
            return updated

        try:
            updated = self._with_transaction(revoke)
        except AccountManagementError as error:
            application = self.database.campus_access_applications.find_one(
                {"id": application_id}
            )
            user = (
                self.database.users.find_one({"id": application["userId"]})
                if application
                else None
            )
            self._record_rejection(
                actor,
                "campus_access_revoke",
                reason,
                user["id"] if user else None,
                user["username"] if user else None,
                error,
                campus_application_id=application_id,
            )
            raise
        return _campus_application_view(self.database, updated, include_account=True)

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
            self._acquire_admin_guard(transaction)
            current_actor = self._require_current_admin(actor["id"], transaction)
            options = _session_options(transaction)
            self.database.users.insert_one(user, **options)
            self._append_operation(
                current_actor,
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
            current_actor = self._require_current_admin(actor["id"], transaction)
            target = self.database.users.find_one({"id": target_id}, **options)
            if not target:
                raise AccountManagementError("账号不存在", 404)
            if target.get("status") != "active":
                raise AccountManagementError("账号当前不可用", 409)
            if _is_available_admin(target):
                self._assert_another_admin_is_available(options)
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
                current_actor,
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
            self._acquire_admin_guard(transaction)
            current_actor = self._require_current_admin(actor["id"], transaction)
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
                current_actor,
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

    def change_status(
        self, actor: dict, target_id: str, status: str, reason: str
    ) -> dict:
        safe_reason = reason.strip()

        def update(transaction) -> dict:
            options = _session_options(transaction)
            self._acquire_admin_guard(transaction)
            current_actor = self._require_current_admin(actor["id"], transaction)
            target = self.database.users.find_one({"id": target_id}, **options)
            if not target:
                raise AccountManagementError("账号不存在", 404)
            if target.get("status") == status:
                raise AccountManagementError("账号当前已是此状态", 409)
            if status == "disabled" and _is_available_admin(target):
                self._assert_another_admin_is_available(options)
            updated = self.database.users.find_one_and_update(
                {
                    "_id": target["_id"],
                    "status": target.get("status"),
                    "role": target.get("role"),
                    "must_change_password": target.get("must_change_password", False),
                    "token_version": target["token_version"],
                },
                {
                    "$set": {
                        "status": status,
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
            detail = "账号已停用" if status == "disabled" else "账号已恢复"
            self._append_operation(
                current_actor,
                "account_status_change",
                safe_reason,
                target_id,
                target["username"],
                "success",
                detail,
                transaction,
            )
            return updated

        try:
            return _account_view(self._with_transaction(update))
        except AccountManagementError as error:
            self._record_rejection(
                actor,
                "account_status_change",
                safe_reason,
                target_id,
                None,
                error,
            )
            raise

    def change_role(self, actor: dict, target_id: str, role: str, reason: str) -> dict:
        safe_reason = reason.strip()

        def update(transaction) -> dict:
            options = _session_options(transaction)
            self._acquire_admin_guard(transaction)
            current_actor = self._require_current_admin(actor["id"], transaction)
            target = self.database.users.find_one({"id": target_id}, **options)
            if not target:
                raise AccountManagementError("账号不存在", 404)
            if target.get("role") == role:
                raise AccountManagementError("账号当前已是此角色", 409)
            if role == "user" and _is_available_admin(target):
                self._assert_another_admin_is_available(options)
            updated = self.database.users.find_one_and_update(
                {
                    "_id": target["_id"],
                    "role": target.get("role"),
                    "status": target.get("status"),
                    "must_change_password": target.get("must_change_password", False),
                },
                {
                    "$set": {
                        "role": role,
                        "updatedAt": datetime.now(UTC).isoformat(),
                    }
                },
                return_document=ReturnDocument.AFTER,
                **options,
            )
            if not updated:
                raise AccountManagementError("账号已变化，请重试", 409)
            detail = "已授予管理员角色" if role == "admin" else "已撤销管理员角色"
            self._append_operation(
                current_actor,
                "account_role_change",
                safe_reason,
                target_id,
                target["username"],
                "success",
                detail,
                transaction,
            )
            return updated

        try:
            return _account_view(self._with_transaction(update))
        except AccountManagementError as error:
            self._record_rejection(
                actor,
                "account_role_change",
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

    def _require_current_admin(
        self, actor_id: str, transaction,
        expected_token_version: object = _TOKEN_VERSION_UNSET,
    ) -> dict:
        actor = self.database.users.find_one(
            {"id": actor_id}, **_session_options(transaction)
        )
        if (
            not actor
            or not _is_available_admin(actor)
            or (
                expected_token_version is not _TOKEN_VERSION_UNSET
                and actor.get("token_version") != expected_token_version
            )
        ):
            raise AccountManagementError("管理员权限已变化，请重新登录后重试", 403)
        return actor

    def _require_current_applicant(self, applicant: dict, transaction) -> dict:
        current = self.database.users.find_one(
            {"id": applicant["id"]}, **_session_options(transaction)
        )
        if (
            not current
            or current.get("status") != "active"
            or current.get("must_change_password") is not False
            or current.get("token_version") != applicant.get("token_version")
        ):
            raise AccountManagementError(
                "当前账号会话已变化，请重新登录后重试", 401
            )
        return current

    def _assert_another_admin_is_available(self, options: dict) -> None:
        available_admins = self.database.users.count_documents(
            _AVAILABLE_ADMIN_QUERY, **options
        )
        if available_admins <= 1:
            raise AccountManagementError("不能移除最后一个可用管理员", 409)

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
        campus_application_id: str | None = None,
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
            campus_application_id=campus_application_id,
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
        campus_application_id: str | None = None,
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
        if campus_application_id:
            operation["campusApplicationId"] = campus_application_id
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
        "status": user.get("status", "active"),
        "mustChangePassword": bool(user.get("must_change_password", False)),
    }


_AVAILABLE_ADMIN_QUERY = {
    "role": "admin",
    "status": "active",
    "must_change_password": False,
}


def _is_available_admin(user: dict) -> bool:
    return (
        user.get("role") == "admin"
        and user.get("status") == "active"
        and user.get("must_change_password") is False
    )


def _campus_application_view(
    database: Database, application: dict, *, include_account: bool = False
) -> dict:
    history = list(
        database.account_management_operations.find(
            {"campusApplicationId": application["id"]},
            {
                "_id": 0,
                "id": 1,
                "actorUsername": 1,
                "action": 1,
                "createdAt": 1,
                "reason": 1,
                "result": 1,
                "detail": 1,
            },
        ).sort([("createdAt", ASCENDING), ("_id", ASCENDING)])
    )
    result = {
        "id": application["id"],
        "applicantName": application["applicantName"],
        "studentNumber": application["studentNumber"],
        "identitySource": application["identitySource"],
        "status": application["status"],
        "submittedAt": application["submittedAt"],
        "history": history,
    }
    if include_account:
        result["userId"] = application["userId"]
        result["username"] = application["username"]
    return result
