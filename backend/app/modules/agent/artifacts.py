"""工作台修订建议：Run 锁定正文基线，校验后暂存提议并随完成统一提交。

工具可在完整正文位置索引中定位一个段落；教师选区存在时仍锁定该范围。
工具调用期只构建不落库，Artifact 与助手消息在 Run 完成事务中一起发布。
"""

from __future__ import annotations

from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.database import Database

from app.core.ids import new_id
from app.modules.agent import blocks, prosemirror
from app.modules.agent.models import (
    AgentArtifact,
    AgentWrite,
    ArtifactDecision,
    ArtifactTarget,
    SourceRef,
    write_view,
)
from app.modules.agent.prosemirror import ParagraphChangedError, ParagraphNotFoundError
from app.modules.agent.repository import (
    AgentRepository,
    claim_run_write_path,
    expired_artifact_view,
    transaction,
)
from app.modules.agent.source_reader import revalidate_sources
from app.modules.cases.service import CaseError, case_view


def _now() -> datetime:
    return datetime.now(UTC)


def propose_artifact(
    database: Database, case_id: str, thread_id: str, run_id: str,
    start: int, end: int, replacement: str, reason: str,
    sources: list[SourceRef], user: dict, annotation_id: str | None = None,
) -> AgentArtifact:
    """校验当前正文范围并构建 pending Artifact；随运行完成事务统一提交。"""
    case = _current_case(database, case_id)
    _verify_writer(case, user)
    target = _revision_target(database, run_id, case, start, end)
    _ensure_no_artifact(database, run_id)
    return _artifact_document(
        case, thread_id, run_id, target, replacement, reason, sources, annotation_id
    )


def propose_document_artifact(
    database: Database, case_id: str, thread_id: str, run_id: str,
    blocks_input: object, reason: str,
    sources: list[SourceRef], user: dict,
) -> AgentArtifact:
    """构建整篇 AI 版本草稿；已有教师正文也允许独立生成。"""
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
    """整篇生成前提：运行基线未越且本次运行尚未生成过整篇稿。"""
    _verify_run_baseline(database, run_id, case)
    _ensure_no_artifact(database, run_id)
    normalized = blocks.validate_blocks(blocks_input)
    if not claim_run_write_path(database, run_id, "document"):
        raise CaseError(409, "本次运行已选择另一条正文路径")
    return normalized


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
        raise CaseError(422, "本条消息没有正文基线，不能提议修订")
    if run["baseRevision"] != case["revision"]:
        raise CaseError(409, "正文已更新，修订目标已过期，请重新选择段落")
    return run


def _ensure_no_artifact(database, run_id: str) -> None:
    if database.agent_artifacts.find_one({"runId": run_id}):
        raise CaseError(409, "本次运行已提议过修订候选")


def _revision_target(database, run_id, case: dict, start: int, end: int) -> ArtifactTarget:
    run = _verify_run_baseline(database, run_id, case)
    lock = run.get("target")
    if lock:
        if (lock["from"], lock["to"]) != (start, end):
            raise CaseError(422, "修订目标必须与教师选定的范围一致")
        return ArtifactTarget(from_pos=lock["from"], to_pos=lock["to"], quote=lock["quote"])
    try:
        prosemirror.selection_block(case["document"], start, end)
        quote = prosemirror.text_between(case["document"], start, end)
    except (ParagraphChangedError, ParagraphNotFoundError) as error:
        raise CaseError(422, "修订目标必须位于当前正文的同一段落") from error
    if not quote.strip():
        raise CaseError(422, "修订目标不能为空")
    return ArtifactTarget(from_pos=start, to_pos=end, quote=quote)


def _current_case(database: Database, case_id: str, session=None) -> dict:
    case = database.cases.find_one({"id": case_id}, session=session)
    if not case:
        raise CaseError(404, "案例不存在")
    return case


def _artifact_document(
    case: dict, thread_id: str, run_id: str, target: ArtifactTarget,
    replacement: str, reason: str, sources: list[SourceRef], annotation_id: str | None,
) -> AgentArtifact:
    return AgentArtifact(
        id=new_id("artifact"), case_id=case["id"], thread_id=thread_id, run_id=run_id,
        base_revision=case["revision"], target=target, replacement=replacement,
        annotation_id=annotation_id, reason=reason, sources=sources, created_at=_now(),
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
    artifact, case, write, steps, applied = transaction(
        database,
        lambda session: _decide(
            database, case_id, thread_id, artifact_id, user, decision, session
        ),
    )
    result = {
        "artifact": _visible_decision_artifact(database, artifact, case, user),
        "case": case_view(case),
        "applied": applied,
    }
    if write:
        result["write"] = write_view(write)
    if steps:
        result["steps"] = steps
    return result


def _visible_decision_artifact(database, artifact, case, user):
    from app.modules.agent.visibility import visible_artifact

    current = expired_artifact_view(artifact, case.get("revision"))
    return visible_artifact(database, current, user)


def _decide(database, case_id, thread_id, artifact_id, user, decision, session):
    _existing_thread(database, case_id, thread_id, user, session)
    artifact = _existing_artifact(database, case_id, thread_id, artifact_id, session)
    case = _current_case(database, case_id, session)
    if artifact.status != "pending":
        if artifact.status != decision:
            raise CaseError(409, "修订候选已决定，不能改变决定")
        write = database.agent_writes.find_one(
            {"artifactId": artifact.id}, session=session,
        ) if artifact.status == "accepted" else None
        return artifact, case, write, [], False
    _decidable_run(database, artifact, decision, session)
    _verify_writer(case, user)
    _decide_annotation_revision(database, artifact, user, decision, session)
    write, steps = None, []
    if decision in ("accepted", "superseded"):
        if not revalidate_sources(database, user, case_id, artifact.sources):
            raise CaseError(409, "修订依据当前不可读，候选不能应用或微调")
        if decision == "superseded":
            _recheck_target(case, artifact)
    if decision == "accepted":
        case, write, steps = _accept_candidate(database, case, artifact, user, session)
    artifact = _save_decision(
        database, artifact, user, decision, session,
        write["id"] if write else None,
    )
    return artifact, case, write, steps, bool(write)


def _decide_annotation_revision(database, artifact, user, decision, session) -> None:
    if not artifact.annotation_id:
        return
    if decision == "accepted":
        raise CaseError(409, "批注修订请从批注面板合并")
    if decision == "superseded":
        raise CaseError(409, "批注修订不支持从工作台微调")
    from app.modules.annotations.service import mark_ai_revision_decision

    mark_ai_revision_decision(database, artifact, user, decision, session)


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


def _accept_candidate(database, case, artifact, user, session) -> tuple[dict, dict | None, list]:
    """把当前段落候选写入教师稿，并为编辑器保留可撤销的 ProseMirror steps。"""
    if artifact.kind == "document":
        return _candidate_ai_version(database, case, artifact, user, session), None, []
    if case["revision"] != artifact.base_revision:
        raise CaseError(409, "正文已更新，修订候选已过期")
    document, steps = _resolved_document(case, artifact)
    from app.modules.cases.snapshots import record_snapshot

    record_snapshot(database, case, user, "pre_agent_decision", session)
    write = AgentWrite(
        id=new_id("write"), case_id=case["id"], thread_id=artifact.thread_id,
        run_id=artifact.run_id, artifact_id=artifact.id, scope="selection",
        summary=artifact.reason, before_document=case["document"], document=document,
        document_steps=steps, base_revision=case["revision"],
        result_revision=case["revision"] + 1, created_by=user["id"], created_at=_now(),
    ).model_dump(by_alias=True, mode="python")
    updated = _commit_revision(database, case, user, artifact, write, steps, session)
    database.agent_writes.insert_one(write, session=session)
    _append_event(database, artifact.thread_id, "document.written", artifact.run_id,
                  {"writeId": write["id"], "scope": "selection"}, session)
    from app.modules.cases.versions import AI_VERSION_KIND, create_version

    version = create_version(
        database, updated, user, AI_VERSION_KIND, updated["title"], document, session,
    )
    _link_candidate_version(database, updated, artifact, version, session)
    return updated, write, steps


def _candidate_ai_version(database, case, artifact, user, session) -> dict:
    """普通候选接受：整篇替换结果冻结为独立只读 AI 版本，当前稿不动。"""
    from app.modules.cases.versions import AI_VERSION_KIND, create_version

    if case["revision"] != artifact.base_revision:
        raise CaseError(409, "正文已更新，修订候选已过期")
    document, _steps = _resolved_document(case, artifact)
    record = create_version(
        database, case, user, AI_VERSION_KIND, case["title"], document, session,
    )
    _link_candidate_version(database, case, artifact, record, session)
    return case


def _commit_revision(database, case, user, artifact, write, steps, session):
    from app.modules.annotations.service import (
        document_mapping, reconcile_document_annotations,
    )

    document = write["document"]
    mapping = document_mapping(case["document"], document, steps)
    updated = database.cases.find_one_and_update(
        {"id": case["id"], "ownerId": user["id"], "workflowStatus": "draft",
         "revision": case["revision"]},
        {"$set": {"document": document, "updatedAt": _now().isoformat()},
         "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if not updated:
        raise CaseError(409, "正文已更新，修订候选已过期")
    reconcile_document_annotations(
        database, case["id"], case["document"], document,
        updated["revision"], steps, session, mapping,
        exclude_artifact_id=artifact.id,
    )
    return updated


def _link_candidate_version(database, case, artifact, record, session) -> None:
    database.case_versions.update_one(
        {"id": record["id"]}, {"$set": {
            "sourceRunId": artifact.run_id, "sourceArtifactId": artifact.id,
        }}, session=session,
    )
    database.agent_artifacts.update_one(
        {"id": artifact.id}, {"$set": {"versionId": record["id"]}}, session=session,
    )


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
                   decision: ArtifactDecision, session,
                   write_id: str | None = None) -> AgentArtifact:
    now = _now()
    changes = {"status": decision, "decidedBy": user["id"], "decidedAt": now}
    if write_id:
        changes["writeId"] = write_id
    row = database.agent_artifacts.find_one_and_update(
        {"id": artifact.id, "status": "pending"},
        {"$set": changes},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if not row:
        raise CaseError(409, "修订候选已被决定")
    _append_event(database, artifact.thread_id, "artifact.decided", artifact.run_id,
                  {"artifactId": artifact.id, "decision": decision}, session)
    return AgentArtifact.model_validate({k: v for k, v in row.items() if k != "_id"})
