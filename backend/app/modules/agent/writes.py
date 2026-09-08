"""Agent 直接写入正文：教师明确指令下服务端执行、恰好一次、可撤销。

写入授权不在工具参数或模型自报：由服务端在 Run 创建时从当前教师消息
判定「直接肯定指令」并冻结在 Run 上（内化 langgraph interrupt 原则：
可信授权状态先于写入且持久绑定操作；不引入新框架与二次确认）。判定
按从句分析：引用、疑问、否定、条件与说明性提及不得授权，只有不含
否定/疑问/条件标记的从句中的「直接＋写入类动词」才授权，例如「我要
直接写入」授权而「不能直接写入」「是否可以直接写入」不授权。

写入时重验作者与工作版本门禁、Run 基线修订号、Thread 与目标案例绑定、
授权标记与只读拒绝；范围守卫（整篇仅真空文档/未编辑模板，选区仅锁定
范围）全部通过才写入；写入保留结构化块与撤销所需前后文档，撤销按修订
号守卫精确恢复。
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
# 核心指令词：直接＋写入类动词。
_DIRECT_WRITE_CORE = re.compile(r"直接(?:写入|写进|修改|替换|插入|覆盖)")
# 引号/括号内的提及是说明性引用，先剔除再判定。
_QUOTED_SPANS = re.compile(
    r"「[^」]*」|『[^』]*』|“[^”]*”|‘[^’]*’|【[^】]*】"
    r'|"[^"]*"|\'[^\']*\'|（[^）]*）|\([^)]*\)'
)
_CLAUSE_SPLIT = re.compile(r"[。！？!?；;.\n]")
# 从句内出现即否定，不得授权。
_NEGATIONS = (
    "不", "没", "未", "勿", "别", "免", "禁", "拒", "防", "慎", "莫",
    "无需", "无须", "无法", "难以", "避免",
)
# 从句内出现即疑问/询问，不得授权。
_QUESTIONS = (
    "吗", "呢", "请问", "能不能", "是否", "可否", "能否", "如何", "怎么", "怎样",
    "为何", "为什么", "什么", "哪",
)
# 从句内出现即条件假设，尚未成为指令，不得授权。
_CONDITIONALS = ("如果", "假如", "假设", "若是", "要是", "一旦", "的话", "以后", "之后")
# 直接写入作为名词被提及（功能/规则说明）而非指令时，不得授权。
_MENTION_SUFFIXES = (
    "功能", "按钮", "规则", "模式", "选项", "机制", "说明", "是什么",
    "的意思", "的含义", "用法", "怎么用", "的结果", "的内容", "结果", "内容",
)
_MENTION_PREFIXES = (
    "提示词", "需求", "验收", "文档", "说明", "解释", "含义", "意思", "介绍",
    "理解", "撤销", "取消", "回滚", "撤回", "展示", "查看", "显示",
)

def direct_write_requested(text: str) -> bool:
    """服务端从教师当前消息判定直接写入授权：仅直接肯定指令。

    剔除引用后按标点拆从句；只有包含核心指令词且无否定、疑问、条件、
    名词化提及标记的从句才授权。普通生成、润色与解释性文字一律不授权。
    """
    cleaned = _QUOTED_SPANS.sub("", text or "")
    for clause in _CLAUSE_SPLIT.split(cleaned):
        match = _DIRECT_WRITE_CORE.search(clause)
        if match is None:
            continue
        if _contains(clause, _QUESTIONS + _CONDITIONALS) or _negates_core(clause, match):
            continue
        if _is_mention(clause):
            continue
        return True
    return False


def _contains(clause: str, tokens) -> bool:
    return any(token in clause for token in tokens)


def _negates_core(clause: str, match: re.Match) -> bool:
    separators = "，,：:、"
    start = max(clause.rfind(separator, 0, match.start()) for separator in separators) + 1
    ends = [clause.find(separator, match.end()) for separator in separators]
    end = min((value for value in ends if value >= 0), default=len(clause))
    return _contains(clause[start:end], _NEGATIONS)


def _is_mention(clause: str) -> bool:
    match = _DIRECT_WRITE_CORE.search(clause)
    after = clause[match.end():match.end() + 8]
    before = clause[max(0, match.start() - 12):match.start()]
    return (_contains(after, _MENTION_SUFFIXES)
            or _contains(before, _MENTION_PREFIXES))


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
    case, run, document = _write_guards(
        database, case_id, run_id, scope, normalized, user, session,
    )
    record_snapshot(database, case, user, "pre_agent_write", session)
    write = _new_write_record(case, run, scope, normalized, user, summary, document)
    return _commit_write(database, case_id, user, run, write, scope, session)


def _write_guards(database, case_id, run_id, scope, normalized, user, session) -> tuple:
    """写入守卫：作者授权、一次运行一次写入、基线未越，并解析目标文档。"""
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
    return case, run, document


def _new_write_record(case, run, scope, normalized, user, summary, document) -> dict:
    record = AgentWrite(
        id=new_id("write"), case_id=case["id"], thread_id=run["threadId"],
        run_id=run["id"], scope=scope, summary=summary, blocks=normalized,
        before_document=case["document"], document=document,
        base_revision=case["revision"], result_revision=case["revision"] + 1,
        created_by=user["id"], created_at=_now(),
    )
    return record.model_dump(by_alias=True, mode="python")


def _commit_write(database, case_id, user, run, write, scope, session) -> dict:
    """CAS 落库：正文修订 +1，写入记录与线程事件同事务可见。"""
    updated = database.cases.find_one_and_update(
        {"id": case_id, "revision": write["baseRevision"], "ownerId": user["id"],
         "workflowStatus": "draft"},
        {"$set": {"document": write["document"], "updatedAt": _now().isoformat()},
         "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if not updated:
        raise CaseError(409, "案例状态已变化")
    database.agent_writes.insert_one(write, session=session)
    _append_event(database, run["threadId"], "document.written", run["id"],
                  {"writeId": write["id"], "scope": scope}, session)
    return write


def _document_scope(case: dict, normalized: list[dict]) -> dict:
    """整篇写入仅接受空草稿或模板；已有正文时必须先澄清范围。"""
    if not blocks.document_rewritable(case["document"]):
        raise CaseError(422, "正文已有内容，不能整篇覆盖；请先澄清要写入的范围")
    return blocks.structured_document(normalized)


def _selection_scope(case: dict, normalized: list[dict], run: dict) -> dict:
    """选区写入仅接受 Run 创建时锁定的教师非空选区，并保留块结构。"""
    target = run.get("target")
    if not target:
        raise CaseError(422, "本条消息没有教师选定的正文范围，不能直接写入选区")
    nodes = blocks.structured_document(normalized)["content"]
    try:
        return prosemirror.replaced_document_blocks(
            case["document"], target["from"], target["to"], target["quote"], nodes,
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
    write = _undo_target(database, case_id, thread_id, write_id, user, session)
    case = _writable_case(database, case_id, user, session)
    if write["status"] == "undone":
        return {"write": write, "case": case}
    if case["revision"] != write["resultRevision"]:
        raise CaseError(409, "正文已更新，不能撤销此写入")
    updated = _restore_document(database, case_id, write, user, session)
    row = _mark_undone(database, write_id, user, session)
    _append_event(database, thread_id, "document.undone", write["runId"],
                  {"writeId": write_id}, session)
    return {"write": row or write, "case": updated}


def _undo_target(database, case_id, thread_id, write_id, user, session) -> dict:
    """撤销目标存在性：Thread 绑定该案例且属当前用户，写入记录必须存在。"""
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
    return write


def _restore_document(database, case_id, write, user, session) -> dict:
    """CAS 恢复写入前正文；正文修订号未再前进才允许撤销。"""
    updated = database.cases.find_one_and_update(
        {"id": case_id, "revision": write["resultRevision"], "ownerId": user["id"],
         "workflowStatus": "draft"},
        {"$set": {"document": write["beforeDocument"], "updatedAt": _now().isoformat()},
         "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if not updated:
        raise CaseError(409, "案例状态已变化")
    return updated


def _mark_undone(database, write_id, user, session) -> dict | None:
    return database.agent_writes.find_one_and_update(
        {"id": write_id, "status": "written"},
        {"$set": {"status": "undone", "undoneBy": user["id"], "undoneAt": _now()}},
        return_document=ReturnDocument.AFTER, session=session,
    )


def _writable_case(database, case_id, user, session) -> dict:
    case = database.cases.find_one({"id": case_id}, session=session)
    if not case:
        raise CaseError(404, "案例不存在")
    _verify_writer(case, user)
    return case


def _writable_run(database, run_id, case_id, user, session) -> dict:
    """Run 必须活跃、属当前用户、非只读、经 Thread 绑定到目标案例且已授权。"""
    run = database.agent_runs.find_one({"id": run_id}, session=session)
    if not run or run["userId"] != user["id"] or run["status"] != "active":
        raise CaseError(409, "运行已结束，不能直接写入")
    if run.get("readOnly"):
        raise CaseError(403, "只读对话不能写入正文")
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
