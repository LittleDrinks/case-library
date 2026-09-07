"""动作资格：lifecycle 状态机向前端输出的唯一动作数据源。

工作版本状态与发布状态相互独立；发布动作（hide/restore/reopen）只在
workflowStatus 为 published 时出现。作者资格按 ownerId 判定，与管理员
资格可叠加，未登录一律无动作。
"""
from __future__ import annotations

OWNER_COMMANDS = {
    "draft": ("submit", "snapshot", "rollback"),
    "pending": ("withdraw",),
    "reviewing": ("withdraw",),
}
ADMIN_COMMANDS = {
    "pending": ("start",),
    "reviewing": ("approve", "reject", "supplement"),
}


def available_actions(case: dict, user: dict | None) -> list[str]:
    if not user:
        return []
    commands = list(_commands(case, user))
    commands.extend(_publication_commands(case, user))
    return commands


def _commands(case: dict, user: dict) -> tuple[str, ...]:
    status = case["workflowStatus"]
    commands: tuple[str, ...] = ()
    if user["role"] == "admin":
        commands += ADMIN_COMMANDS.get(status, ())
        if status == "published" and case["publicationStatus"] == "hidden":
            commands += ("reopen",)
    if case.get("ownerId") == user["id"]:
        commands += OWNER_COMMANDS.get(status, ())
    return commands


def _publication_commands(case: dict, user: dict) -> tuple[str, ...]:
    if user["role"] != "admin" or case["workflowStatus"] != "published":
        return ()
    if case["publicationStatus"] == "public":
        return ("hide",)
    if case["publicationStatus"] == "hidden":
        return ("restore",)
    return ()
