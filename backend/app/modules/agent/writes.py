"""Agent 直接写入正文：教师明确指令下服务端执行、恰好一次、可撤销。

与修订候选不同，直接写入在工具调用事务内真实落库。写入授权不在工具参数
或模型自报：由服务端在 Run 创建时从当前教师消息文本中判定「直接写入」
类指令并冻结在 Run 上；写入时重验作者与工作版本门禁、Run 基线修订号、
Run 与目标案例的 Thread 绑定及授权标记，范围守卫（整篇仅空草稿/模板，
选区仅锁定范围）全部通过才写入；写入记录保留前后文档，撤销在事务内按
修订号守卫精确恢复。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.database import Database

from app.core.ids import new_id
from app.modules.agent import blocks, prosemirror
from app.modules.agent.models import AgentWrite
from app.modules.agent.repository import AgentRepository, transaction
from app.modules.cases.service import CaseError
from app.modules.cases.snapshots import record_snapshot

SCOPES = ("document", "selection")
# 明确「直接写入」类指令：否定语（勿/要/别 + 直接）不授权，退回候选确认。
_DIRECT_WRITE_PATTERN = re.compile(r"(?<![勿要别])直接(?:写入|写进|修改|替换|插入|覆盖)")


def direct_write_requested(text: str) -> bool:
    """服务端从教师当前消息文本判定直接写入授权；普通生成/润色不授权。"""
    return bool(_DIRECT_WRITE_PATTERN.search(text or ""))


def _now() -> datetime:
    return datetime.now(UTC)


def apply_write(
    database: Database, case_id: str, run_id: str, scope: str,
    blocks_input: object, user: dict, summary: str = "",
) -> dict[str, Any]:
    """执行一次显式直接写入；任何守卫不通过都不落库并返回可重试错误。"""
    normalized = blocks.validate_blocks(blocks_input) if scope in SCOPES else None
    if normalized is None:
        raise CaseError(422, "写入范围无效：只能是 document 或 selection")
    return transaction(database, lambda session: _apply(
        database, case_id, run_id, scope, normalized, user, summary, session,
    ))


def _apply(database, case_id, run_id, scope, normalized, user, summary, session) -> dict:
    case = _writable_case(database, case_id, user, session)
    run = _writable_run(database, run_id, case_id, user, session)
    if database.agent_writes.find_one({"runId": run_id}, session=session):
        raise CaseError(409, "本次运行已直接写入过正文")
    if case["revision"] != run["baseRevision"]:
        raise CaseError(409, "正文已更新，写入基线已过期，请重新确认范围")
    if scope == "document":
        document = _document_scope(case, normalized)
    else:
        document = _selection_scope(case, normalized, run)
    record_snapshot(database, case, user, "pre_agent_write", session)
    record = AgentWrite(
        id=new_id("write"), case_id=case_id, thread_id=run["threadId"],
        run_id=run_id, scope=scope, summary=summary, blocks=normalized,
        before_document=case["document"], document=document,
        base_revision=case["revision"], result_revision=case["revision"] + 1,
        created_by=user["id"], created_at=_now(),
    )
    write = record.model_dump(by_alias=True, mode="python")
    updated = database.cases.find_one_and_update(
        {"id": case_id, "revision": case["revision"], "ownerId": user["id"],
         "workflowStatus": "draft"},
        {"$set": {"document": document, "updatedAt": _now().isoformat()},
         "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if not updated:
        raise CaseError(409, "案例状态已变化")
    database.agent_writes.insert_one(write, session=session)
    _append_event(database, run["threadId"], "document.written", run_id,
                  {"writeId": write["id"], "scope": scope}, session)
    return write


def _document_scope(case: dict, normalized: list[dict]) -> dict:
    """整篇写入仅接受空草稿或模板；已有正文时必须先澄清范围。"""
    if not blocks.document_rewritable(case["document"]):
        raise CaseError(422, "正文已有内容，不能整篇覆盖；请先澄清要写入的范围")
    return blocks.structured_document(normalized)


def _selection_scope(case: dict, normalized: list[dict], run: dict) -> dict:
    """选区写入仅接受 Run 创建时锁定的教师非空选区。"""
    target = run.get("target")
    if not target:
        raise CaseError(422, "本条消息没有教师选定的正文范围，不能直接写入选区")
    lines = blocks.block_lines(normalized)
    try:
        return prosemirror.replaced_document_lines(
            case["document"], target["from"], target["to"], target["quote"], lines,
        )
    except (prosemirror.ParagraphChangedError, prosemirror.ParagraphNotFoundError) as error:
        raise CaseError(409, "目标选区原文已变化，请重新选择范围") from error


def undo_write(
    database: Database, case_id: str, thread_id: str, write_id: str, user: dict,
) -> dict:
    """撤销一次直接写入；重复撤销幂等返回，正文已更新则拒绝。"""
    return transaction(database, lambda session: _undo(
        database, case_id, thread_id, write_id, user, session,
    ))


def _undo(database, case_id, thread_id, write_id, user, session) -> dict:
    thread = database.agent_threads.find_one(
        {"id": thread_id, "caseId": case_id, "ownerId": user["id"]}, session=session
    )
    if not thread:
        raise CaseError(404, "对话不存在")
    write = database.agent_writes.find_one(
        {"id": write_id, "caseId": case_id, "threadId": thread_id}, session=session
    )
    if not write:
        raise CaseError(404, "写入记录不存在")
    case = _writable_case(database, case_id, user, session)
    if write["status"] == "undone":
        return {"write": write, "case": case}
    if case["revision"] != write["resultRevision"]:
        raise CaseError(409, "正文已更新，不能撤销此写入")
    updated = database.cases.find_one_and_update(
        {"id": case_id, "revision": case["revision"], "ownerId": user["id"],
         "workflowStatus": "draft"},
        {"$set": {"document": write["beforeDocument"], "updatedAt": _now().isoformat()},
         "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if not updated:
        raise CaseError(409, "案例状态已变化")
    row = database.agent_writes.find_one_and_update(
        {"id": write_id, "status": "written"},
        {"$set": {"status": "undone", "undoneBy": user["id"], "undoneAt": _now()}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    _append_event(database, thread_id, "document.undone", write["runId"],
                  {"writeId": write_id}, session)
    return {"write": row or write, "case": updated}


def _writable_case(database, case_id, user, session) -> dict:
    case = database.cases.find_one({"id": case_id}, session=session)
    if not case:
        raise CaseError(404, "案例不存在")
    _verify_writer(case, user)
    return case


def _writable_run(database, run_id, case_id, user, session) -> dict:
    """Run 必须活跃、属于当前用户、通过 Thread 绑定到目标案例且已获授权。"""
    run = database.agent_runs.find_one({"id": run_id}, session=session)
    if not run or run["userId"] != user["id"] or run["status"] != "active":
        raise CaseError(409, "运行已结束，不能直接写入")
    thread = database.agent_threads.find_one(
        {"id": run["threadId"]}, session=session
    )
    if not thread or thread["caseId"] != case_id or thread["ownerId"] != user["id"]:
        raise CaseError(404, "对话不存在")
    if not run.get("writeAuthorized"):
        raise CaseError(
            403, "本条消息没有明确的直接写入指令，不能直接写入；请改为候选供教师确认"
        )
    if run.get("baseRevision") is None:
        raise CaseError(422, "运行缺少正文基线，不能直接写入")
    return run


def _verify_writer(case: dict, user: dict) -> None:
    if case.get("ownerId") != user["id"]:
        raise CaseError(403, "仅案例作者可写入或撤销正文")
    if case.get("workflowStatus") != "draft":
        raise CaseError(409, "案例当前不可编辑")


def _append_event(database, thread_id, event_type, run_id, payload, session) -> None:
    if AgentRepository(database)._append_event(
        thread_id, event_type, run_id, payload, session
    ) is None:
        raise RuntimeError("Thread 事件写入失败")


def write_view(write: dict) -> dict:
    """对外暴露的写入记录视图：不含文档内容，只含撤销所需的结构字段。"""
    return {
        "id": write["id"], "runId": write["runId"], "scope": write["scope"],
        "summary": write.get("summary", ""), "status": write["status"],
        "revision": write["resultRevision"],
    }
