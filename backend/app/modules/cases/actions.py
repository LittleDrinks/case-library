"""动作资格：lifecycle 状态机向前端输出的唯一动作数据源。"""
from __future__ import annotations

OWNER_COMMANDS = {
    "draft": ("submit", "snapshot", "rollback"),
    "pending": ("withdraw",),
    "reviewing": ("withdraw",),
    "published": ("reopen",),
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
    return list(dict.fromkeys(commands))


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
    if user["role"] != "admin":
        return ()
    if case["publicationStatus"] == "public":
        return ("hide",)
    if case["publicationStatus"] == "hidden":
        return ("restore",)
    return ()
