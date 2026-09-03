"""Artifact 领域服务：服务端重建来源、校验 target/revision、原子写入正文快照与决定。"""

from __future__ import annotations

from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.database import Database

from app.core.ids import new_id
from app.modules.agent import prosemirror
from app.modules.agent.models import (
    AgentArtifact,
    ArtifactDecision,
    ArtifactTarget,
    SourceRef,
)
from app.modules.agent.prosemirror import ParagraphChangedError, ParagraphNotFoundError
from app.modules.agent.repository import AgentRepository, transaction
from app.modules.cases.service import CaseError, case_view
from app.modules.cases.snapshots import record_snapshot


def _now() -> datetime:
    return datetime.now(UTC)


def propose_artifact(
    database: Database, case_id: str, thread_id: str, run_id: str,
    paragraph_index: int, replacement: str, reason: str,
    sources: list[SourceRef],
) -> AgentArtifact:
    """在当前 baseRevision 上创建单段落 pending Artifact 并记录 Thread 事件。"""
    case = _current_case(database, case_id)
    artifact = _artifact_document(
        case, thread_id, run_id, _target(case["document"], paragraph_index),
        replacement, reason, sources,
    )
    transaction(database, lambda session: _insert_artifact(database, artifact, session))
    return artifact


def _target(document: dict, paragraph_index: int) -> ArtifactTarget:
    rows = prosemirror.paragraphs(document)
    if paragraph_index < 0 or paragraph_index >= len(rows):
        raise CaseError(422, "目标段落不存在")
    return ArtifactTarget(paragraphIndex=paragraph_index, quote=rows[paragraph_index]["quote"])


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


def _insert_artifact(database: Database, artifact: AgentArtifact, session) -> None:
    database.agent_artifacts.insert_one(
        artifact.model_dump(by_alias=True, mode="python"), session=session
    )
    _append_event(database, artifact.thread_id, "artifact.created", artifact.run_id,
                  {"artifactId": artifact.id}, session)


def _append_event(database, thread_id, event_type, run_id, payload, session) -> None:
    if AgentRepository(database)._append_event(
        thread_id, event_type, run_id, payload, session
    ) is None:
        raise RuntimeError("Thread 事件写入失败")


def decide_artifact(
    database: Database, case_id: str, artifact_id: str, user: dict,
    decision: ArtifactDecision,
) -> dict:
    """接受或拒绝 Artifact；接受在事务内重验并恰好写一次正文，重复决定返回原决定。"""
    artifact, case = transaction(
        database,
        lambda session: _decide(database, case_id, artifact_id, user, decision, session),
    )
    return {"artifact": artifact, "case": case_view(case)}


def _decide(database, case_id, artifact_id, user, decision, session):
    artifact = _existing_artifact(database, case_id, artifact_id, session)
    case = _current_case(database, case_id, session)
    if artifact.status != "pending":
        return artifact, case
    _verify_writer(case, user)
    if decision == "accepted":
        case = _apply_revision(database, case, artifact, user, session)
    return _save_decision(database, artifact, user, decision, session), case


def _existing_artifact(database, case_id, artifact_id, session) -> AgentArtifact:
    row = database.agent_artifacts.find_one(
        {"id": artifact_id, "caseId": case_id}, session=session
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
    _recheck_target(case, artifact)
    record_snapshot(database, case, user, "pre_agent_decision", session)
    document = prosemirror.replaced_document(
        case["document"], artifact.target.paragraph_index,
        artifact.target.quote, artifact.replacement,
    )
    updated = database.cases.find_one_and_update(
        {"id": case["id"], "revision": case["revision"]},
        {"$set": {"document": document, "updatedAt": _now().isoformat()},
         "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if not updated:
        raise CaseError(409, "案例状态已变化")
    return updated


def _recheck_target(case: dict, artifact: AgentArtifact) -> None:
    try:
        prosemirror.check_target(
            case["document"], artifact.target.paragraph_index, artifact.target.quote
        )
    except (ParagraphChangedError, ParagraphNotFoundError) as error:
        raise CaseError(409, "目标段落原文已变化，修订候选已过期") from error


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
