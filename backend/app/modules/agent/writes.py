"""Agent 直接写入正文：模型按对话选用工具，服务端校验执行、恰好一次、可撤销。

是否直接写入由模型结合完整对话理解并选择；服务端不解析中文措辞。
写入时重验作者与工作版本门禁、Run 基线修订号、Thread 与目标案例绑定、
只读拒绝；范围守卫（整篇仅真空文档/未编辑模板，选区仅锁定范围）全部
通过才写入；写入保留结构化块与撤销所需前后文档，撤销按修订号守卫精
确恢复。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.database import Database

from app.core.ids import new_id
from app.modules.agent import blocks, prosemirror
from app.modules.agent.models import AgentWrite
from app.modules.agent.repository import AgentRepository, claim_run_write_path, transaction
from app.modules.cases.service import CaseError
from app.modules.cases.snapshots import record_snapshot

SCOPES = ("document", "selection")


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
    case, run, document, steps = _write_guards(
        database, case_id, run_id, scope, normalized, user, session,
    )
    if not claim_run_write_path(database, run_id, "direct_write", session):
        raise CaseError(409, "本次运行已选择另一条正文路径")
    record_snapshot(database, case, user, "pre_agent_write", session)
    write = _new_write_record(case, run, scope, normalized, user, summary, document, steps)
    return _commit_write(database, case_id, user, run, write, steps, scope, session)


def _write_guards(database, case_id, run_id, scope, normalized, user, session) -> tuple:
    """写入守卫：作者授权、一次运行一次写入、基线未越，并解析目标文档。"""
    case = _writable_case(database, case_id, user, session)
    run = _writable_run(database, run_id, case_id, user, session)
    if database.agent_writes.find_one({"runId": run_id}, session=session):
        raise CaseError(409, "本次运行已直接写入过正文")
    if case["revision"] != run["baseRevision"]:
        raise CaseError(409, "正文已更新，写入基线已过期，请重新确认范围")
    if scope == "document":
        document, steps = _document_scope(case, normalized)
    else:
        document, steps = _selection_scope(case, normalized, run)
    return case, run, document, steps


def _new_write_record(case, run, scope, normalized, user, summary, document, steps) -> dict:
    record = AgentWrite(
        id=new_id("write"), case_id=case["id"], thread_id=run["threadId"],
        run_id=run["id"], scope=scope, summary=summary, blocks=normalized,
        before_document=case["document"], document=document,
        document_steps=steps,
        base_revision=case["revision"], result_revision=case["revision"] + 1,
        created_by=user["id"], created_at=_now(),
    )
    return record.model_dump(by_alias=True, mode="python")


def _commit_write(database, case_id, user, run, write, steps, scope, session) -> dict:
    """CAS 落库：正文修订 +1，写入记录与线程事件同事务可见。"""
    from app.modules.annotations.service import document_mapping

    mapping = document_mapping(write["beforeDocument"], write["document"], steps)
    _commit_written_document(database, case_id, user, write, steps, mapping, session)
    database.agent_writes.insert_one(write, session=session)
    _append_event(database, run["threadId"], "document.written", run["id"],
                  {"writeId": write["id"], "scope": scope}, session)
    return write


def _commit_written_document(database, case_id, user, write, steps, mapping, session):
    updated = database.cases.find_one_and_update(
        {"id": case_id, "revision": write["baseRevision"], "ownerId": user["id"],
         "workflowStatus": "draft"},
        {"$set": {"document": write["document"], "updatedAt": _now().isoformat()},
         "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if not updated:
        raise CaseError(409, "案例状态已变化")
    from app.modules.annotations.service import reconcile_document_annotations

    reconcile_document_annotations(
        database, case_id, write["beforeDocument"], write["document"],
        write["resultRevision"], steps, session, mapping,
    )


def _document_scope(case: dict, normalized: list[dict]) -> tuple[dict, list[dict]]:
    """整篇写入仅接受空草稿或模板；已有正文时必须先澄清范围。"""
    if not blocks.document_rewritable(case["document"]):
        raise CaseError(422, "正文已有内容，不能整篇覆盖；请先澄清要写入的范围")
    return prosemirror.replace_document(case["document"], blocks.structured_document(normalized))


def _selection_scope(case: dict, normalized: list[dict], run: dict) -> tuple[dict, list[dict]]:
    """选区写入仅接受 Run 创建时锁定的教师非空选区，并保留块结构。"""
    target = run.get("target")
    if not target:
        raise CaseError(422, "本条消息没有教师选定的正文范围，不能直接写入选区")
    nodes = blocks.structured_document(normalized)["content"]
    try:
        return prosemirror.replaced_document_blocks_with_steps(
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
    from app.modules.annotations.service import document_mapping

    steps = prosemirror.invert_steps(write["beforeDocument"], write["documentSteps"])
    mapping = document_mapping(write["document"], write["beforeDocument"], steps)
    return _restore_case_document(
        database, case_id, write, user, steps, mapping, session,
    )


def _restore_case_document(database, case_id, write, user, steps, mapping, session):
    from app.modules.annotations.service import reconcile_document_annotations

    updated = database.cases.find_one_and_update(
        {"id": case_id, "revision": write["resultRevision"], "ownerId": user["id"],
         "workflowStatus": "draft"},
        {"$set": {"document": write["beforeDocument"], "updatedAt": _now().isoformat()},
         "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if not updated:
        raise CaseError(409, "案例状态已变化")
    reconcile_document_annotations(
        database, case_id, write["document"], write["beforeDocument"],
        updated["revision"], steps, session, mapping,
    )
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
    """Run 必须活跃、属当前用户、非只读、经 Thread 绑定到目标案例。"""
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
