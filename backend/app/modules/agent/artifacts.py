"""Artifact 领域服务：Run 锁定选区与基线，校验后暂存提议，随运行完成统一提交。

提议目标只能来自 Run 创建时锁定的教师非空选区；工具调用期只构建不落库，
Artifact 与助手消息、tool.result、事件尾部在 Run 完成事务内同时对外可见，
失败或取消不留下可决定卡片；接受前复验来源可读性，基线越过时展示 expired。
"""

from __future__ import annotations

from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.database import Database

from app.core.ids import new_id
from app.modules.agent import blocks, prosemirror
from app.modules.agent.models import (
    AgentArtifact,
    ArtifactDecision,
    ArtifactTarget,
    SourceRef,
)
from app.modules.agent.prosemirror import ParagraphChangedError, ParagraphNotFoundError
from app.modules.agent.repository import AgentRepository, expired_artifact_view, transaction
from app.modules.agent.source_reader import revalidate_sources
from app.modules.cases.service import CaseError, case_view
from app.modules.cases.snapshots import record_snapshot


def _now() -> datetime:
    return datetime.now(UTC)


def propose_artifact(
    database: Database, case_id: str, thread_id: str, run_id: str,
    start: int, end: int, replacement: str, reason: str,
    sources: list[SourceRef], user: dict,
) -> AgentArtifact:
    """校验 Run 锁定选区并构建 pending Artifact；不落库，随运行完成提交。

    模型不得推断目标：提议必须与教师选定范围一致且基线未过期。
    """
    case = _current_case(database, case_id)
    _verify_writer(case, user)
    target = _locked_target(database, run_id, case, start, end)
    _ensure_no_artifact(database, run_id)
    return _artifact_document(case, thread_id, run_id, target, replacement, reason, sources)


def propose_document_artifact(
    database: Database, case_id: str, thread_id: str, run_id: str,
    blocks_input: object, reason: str,
    sources: list[SourceRef], user: dict,
) -> AgentArtifact:
    """为空草稿或模板构建整篇初稿候选；已有正文时拒绝整篇提议。"""
    case = _current_case(database, case_id)
    _verify_writer(case, user)
    normalized = _document_candidate(database, run_id, case, blocks_input)
    return AgentArtifact(
        id=new_id("artifact"), case_id=case["id"], thread_id=thread_id,
        run_id=run_id, base_revision=case["revision"], kind="document",
        target=ArtifactTarget(from_pos=0, to_pos=0, quote=""),
        replacement="", blocks=normalized, reason=reason, sources=sources,
        created_at=_now(),
    )


def _document_candidate(database, run_id: str, case: dict, blocks_input: object) -> list:
    """整篇候选前提：运行基线未越、未重复提议、正文确为空草稿或模板。"""
    _verify_run_baseline(database, run_id, case)
    _ensure_no_artifact(database, run_id)
    if not blocks.document_rewritable(case["document"]):
        raise CaseError(422, "正文已有内容，整篇候选只适用于空草稿或模板；请先澄清要修改的范围")
    return blocks.validate_blocks(blocks_input)


def _run_row(database, run_id: str) -> dict:
    run = database.agent_runs.find_one({"id": run_id})
    if run is None:
        raise CaseError(422, "运行不存在或已结束，不能提议修订")
    return run


def _verify_run_baseline(database, run_id: str, case: dict) -> dict:
    """作者运行创建时已锁定基线修订号；只读运行与基线越过均显式拒绝。"""
    run = _run_row(database, run_id)
    if run.get("readOnly"):
        raise CaseError(403, "只读对话不能写入正文")
    if run.get("baseRevision") is None:
        raise CaseError(422, "本条消息没有教师选定的正文段落，不能提议修订")
    if run["baseRevision"] != case["revision"]:
        raise CaseError(409, "正文已更新，修订目标已过期，请重新选择段落")
    return run


def _ensure_no_artifact(database, run_id: str) -> None:
    if database.agent_artifacts.find_one({"runId": run_id}):
        raise CaseError(409, "本次运行已提议过修订候选")


def _locked_target(database, run_id, case: dict, start: int, end: int) -> ArtifactTarget:
    """模型提议必须命中 Run 锁定的教师选区。"""
    run = _verify_run_baseline(database, run_id, case)
    lock = run.get("target")
    if not lock:
        raise CaseError(422, "本条消息没有教师选定的正文段落，不能提议修订")
    if (lock["from"], lock["to"]) != (start, end):
        raise CaseError(422, "修订目标必须与教师选定的范围一致")
    return ArtifactTarget(from_pos=lock["from"], to_pos=lock["to"], quote=lock["quote"])


def _current_case(database: Database, case_id: str, session=None) -> dict:
    case = database.cases.find_one({"id": case_id}, session=session)
    if not case:
        raise CaseError(404, "案例不存在")
    return case


def _artifact_document(
    case: dict, thread_id: str, run_id: str, target: ArtifactTarget,
    replacement: str, reason: str, sources: list[SourceRef],
) -> AgentArtifact:
    return AgentArtifact(
        id=new_id("artifact"), case_id=case["id"], thread_id=thread_id, run_id=run_id,
        base_revision=case["revision"], target=target, replacement=replacement,
        reason=reason, sources=sources, created_at=_now(),
    )


def _append_event(database, thread_id, event_type, run_id, payload, session) -> None:
    if AgentRepository(database)._append_event(
        thread_id, event_type, run_id, payload, session
    ) is None:
        raise RuntimeError("Thread 事件写入失败")


def decide_artifact(
    database: Database, case_id: str, thread_id: str, artifact_id: str, user: dict,
    decision: ArtifactDecision,
) -> dict:
    """接受或拒绝 Artifact；接受在事务内重验并恰好写一次正文，重复决定返回原决定。

    事务内先校验 Thread 归属（案例+用户），再校验 Artifact 绑定该 Thread；
    幂等与冲突路径同样执行校验，伪造 threadId 时不产生任何变更或事件。
    """
    artifact, case = transaction(
        database,
        lambda session: _decide(
            database, case_id, thread_id, artifact_id, user, decision, session
        ),
    )
    return {"artifact": expired_artifact_view(artifact, case.get("revision")), "case": case_view(case)}


def _decide(database, case_id, thread_id, artifact_id, user, decision, session):
    _existing_thread(database, case_id, thread_id, user, session)
    artifact = _existing_artifact(database, case_id, thread_id, artifact_id, session)
    case = _current_case(database, case_id, session)
    if artifact.status != "pending":
        if artifact.status != decision:
            raise CaseError(409, "修订候选已决定，不能改变决定")
        return artifact, case
    _decidable_run(database, artifact, decision, session)
    _verify_writer(case, user)
    if decision == "accepted":
        if not revalidate_sources(database, user, case_id, artifact.sources):
            raise CaseError(409, "修订依据当前不可读，候选已过期")
        case = _apply_revision(database, case, artifact, user, session)
    return _save_decision(database, artifact, user, decision, session), case


def _decidable_run(database, artifact: AgentArtifact, decision: ArtifactDecision,
                   session) -> None:
    """运行终态前不接受决定；已取消/失败的提议不能被接受。"""
    run = database.agent_runs.find_one({"id": artifact.run_id}, session=session)
    status = (run or {}).get("status")
    if run is None or status == "active":
        raise CaseError(409, "修订候选所在运行尚未结束，暂不能决定")
    if decision == "accepted" and status in ("cancelled", "failed"):
        raise CaseError(409, "运行已取消或失败，修订候选不能接受")


def _existing_thread(database, case_id, thread_id, user, session) -> None:
    row = database.agent_threads.find_one(
        {"id": thread_id, "caseId": case_id, "ownerId": user["id"]}, session=session
    )
    if not row:
        raise CaseError(404, "对话不存在")


def _existing_artifact(database, case_id, thread_id, artifact_id, session) -> AgentArtifact:
    row = database.agent_artifacts.find_one(
        {"id": artifact_id, "caseId": case_id, "threadId": thread_id}, session=session
    )
    if not row:
        raise CaseError(404, "修订候选不存在")
    return AgentArtifact.model_validate({k: v for k, v in row.items() if k != "_id"})


def _verify_writer(case: dict, user: dict) -> None:
    if case.get("ownerId") != user["id"]:
        raise CaseError(403, "仅案例作者可决定修订候选")
    if case.get("workflowStatus") != "draft":
        raise CaseError(409, "案例当前不可编辑")


def _apply_revision(database, case: dict, artifact: AgentArtifact, user: dict, session) -> dict:
    if case["revision"] != artifact.base_revision:
        raise CaseError(409, "正文已更新，修订候选已过期")
    document, steps = _resolved_document(case, artifact)
    mapping = _revision_mapping(case, document, steps)
    record_snapshot(database, case, user, "pre_agent_decision", session)
    return _commit_revision(database, case, document, steps, mapping, artifact.id, session)


def _revision_mapping(case, document, steps):
    from app.modules.annotations.service import document_mapping

    return document_mapping(case["document"], document, steps)


def _commit_revision(database, case, document, steps, mapping, artifact_id, session) -> dict:
    updated = database.cases.find_one_and_update(
        {"id": case["id"], "revision": case["revision"]},
        {"$set": {"document": document, "updatedAt": _now().isoformat()},
         "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if not updated:
        raise CaseError(409, "案例状态已变化")
    from app.modules.annotations.service import reconcile_document_annotations

    reconcile_document_annotations(
        database, case["id"], case["document"], document, updated["revision"],
        steps, session, mapping, artifact_id,
    )
    return updated


def _resolved_document(case: dict, artifact: AgentArtifact) -> tuple[dict, list[dict]]:
    """范围候选按锁定选区替换；整篇候选由规范化块重建结构化文档。"""
    if artifact.kind == "document":
        return prosemirror.replace_document(
            case["document"], blocks.structured_document(artifact.blocks)
        )
    _recheck_target(case, artifact)
    return prosemirror.replaced_document_with_steps(
        case["document"], artifact.target.from_pos, artifact.target.to_pos,
        artifact.target.quote, artifact.replacement,
    )


def _recheck_target(case: dict, artifact: AgentArtifact) -> None:
    try:
        prosemirror.check_target(
            case["document"], artifact.target.from_pos,
            artifact.target.to_pos, artifact.target.quote,
        )
    except (ParagraphChangedError, ParagraphNotFoundError) as error:
        raise CaseError(409, "目标选区原文已变化，修订候选已过期") from error


def _save_decision(database, artifact: AgentArtifact, user: dict,
                   decision: ArtifactDecision, session) -> AgentArtifact:
    now = _now()
    row = database.agent_artifacts.find_one_and_update(
        {"id": artifact.id, "status": "pending"},
        {"$set": {"status": decision, "decidedBy": user["id"], "decidedAt": now}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if not row:
        raise CaseError(409, "修订候选已被决定")
    _append_event(database, artifact.thread_id, "artifact.decided", artifact.run_id,
                  {"artifactId": artifact.id, "decision": decision}, session)
    return AgentArtifact.model_validate({k: v for k, v in row.items() if k != "_id"})
