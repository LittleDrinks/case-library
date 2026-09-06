"""Artifact 领域服务：Run 锁定目标与基线，校验 target/revision，原子写入正文快照与决定。

提议目标只能来自 Run 创建时锁定的教师选段（或唯一段落自动锁定），一次运行
最多一个候选；运行到达终态前不接受决定，已取消/失败的提议不能接受；接受前
复验来源在当前身份下仍可读；基线修订号被正文更新越过时读取侧展示 expired。
"""

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
from app.modules.agent.repository import (
    AgentRepository,
    expired_artifact_view,
    transaction,
)
from app.modules.cases.service import CaseError, case_view
from app.modules.cases.snapshots import record_snapshot
from app.modules.materials.service import can_read_material


def _now() -> datetime:
    return datetime.now(UTC)


def propose_artifact(
    database: Database, case_id: str, thread_id: str, run_id: str,
    paragraph_index: int, replacement: str, reason: str,
    sources: list[SourceRef], user: dict,
) -> AgentArtifact:
    """在 Run 创建时锁定的 baseRevision 与目标段上创建 pending Artifact。

    模型不得推断目标：提议必须命中教师选定（或唯一）段落且基线未过期；
    一次运行最多一个修订候选。
    """
    return transaction(
        database,
        lambda session: _propose(
            database, case_id, thread_id, run_id, paragraph_index,
            replacement, reason, sources, user, session,
        ),
    )


def _propose(database, case_id, thread_id, run_id, paragraph_index,
             replacement, reason, sources, user, session) -> AgentArtifact:
    case = _current_case(database, case_id, session)
    _verify_writer(case, user)
    target = _locked_target(database, run_id, case, paragraph_index, session)
    artifact = _artifact_document(case, thread_id, run_id, target, replacement, reason, sources)
    _insert_artifact(database, artifact, session)
    return artifact


def _locked_target(database, run_id, case: dict, paragraph_index: int,
                   session) -> ArtifactTarget:
    """模型提议必须命中 Run 锁定的教师选段，且基线修订号未变。"""
    run = database.agent_runs.find_one({"id": run_id}, session=session)
    lock = (run or {}).get("target")
    if not lock or run.get("baseRevision") is None:
        raise CaseError(422, "本条消息没有教师选定的正文段落，不能提议修订")
    if run["baseRevision"] != case["revision"]:
        raise CaseError(409, "正文已更新，修订目标已过期，请重新选择段落")
    if lock["paragraphIndex"] != paragraph_index:
        raise CaseError(422, "修订目标必须与教师选定的段落一致")
    return ArtifactTarget(paragraph_index=lock["paragraphIndex"], quote=lock["quote"])


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
    if database.agent_artifacts.find_one({"runId": artifact.run_id}, session=session):
        raise CaseError(409, "本次运行已提议过修订候选")
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
    database: Database, case_id: str, thread_id: str, artifact_id: str, user: dict,
    decision: ArtifactDecision,
) -> dict:
    """接受或拒绝 Artifact；接受在事务内恰好写一次正文，重复决定返回原决定。

    运行未到终态前拒绝决定；同向重复返回原结果，反向决定返回稳定冲突；
    基线被越过时读取侧展示 expired。
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
        _validate_evidence(database, user, artifact)
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


def _validate_evidence(database, user, artifact: AgentArtifact) -> None:
    """接受前复验每个来源：按当前身份仍可读且未下线，否则拒绝接受。"""
    for ref in artifact.sources:
        if not _evidence_readable(database, user, ref):
            raise CaseError(409, "引用来源已不可读或已下线，修订候选不能接受")


def _evidence_readable(database, user, ref: SourceRef) -> bool:
    readers = {
        "case": _case_evidence_readable,
        "knowledge": _knowledge_evidence_readable,
        "material": _material_evidence_readable,
    }
    return readers[ref.kind](database, user, ref)


def _case_evidence_readable(database, user, ref: SourceRef) -> bool:
    """案例证据按当前已发布版本复验：公开或内部身份，且发布版本仍存在。"""
    case = database.cases.find_one({"id": ref.id})
    internal = bool(case and user and (
        user["role"] == "admin" or case.get("ownerId") == user["id"]
    ))
    if not case or (case.get("publicationStatus") != "public" and not internal):
        return False
    version_id = case.get("publishedVersionId")
    return bool(version_id) and database.case_versions.find_one(
        {"id": version_id, "caseId": case["id"]}
    ) is not None


def _knowledge_evidence_readable(database, user, ref: SourceRef) -> bool:
    section = database.knowledge_sections.find_one({"id": ref.id})
    if not section:
        return False
    source = database.knowledge_sources.find_one(
        {"id": section.get("sourceId"), "status": "active"}
    )
    return source is not None


def _material_evidence_readable(database, user, ref: SourceRef) -> bool:
    material = database.materials.find_one({"id": ref.id, "status": "active"})
    return material is not None and can_read_material(material, user)


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
