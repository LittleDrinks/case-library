"""来源权限投影：快照、恢复流与模型历史共用的读取面收敛。

按当前身份即时重验来源可读性，只收敛读取视图，不回写历史存储：
一条助手消息引用过的任一来源本轮不可读时，其正文文本、推理、
修订提议内容均可能复述受限内容，整条替换为提示；工具输出与
修订依据列表逐条遮蔽。
"""

from __future__ import annotations

from pydantic import ValidationError

from app.modules.agent.models import (
    AgentArtifact,
    AgentMessage,
    AgentSnapshot,
    SourceRef,
)
from app.modules.agent.source_reader import source_readable

HIDDEN_ANSWER = "该回答引用的来源当前不可读，相关内容已隐藏"
HIDDEN_REVISION = "该候选引用的来源当前不可读，修订内容已隐藏"
NO_ACCESS_OUTPUT = {"status": "no_access", "detail": "来源当前不可读"}


class SourceGate:
    """同一读取轮内按来源身份缓存可读性，保证各输出面投影口径一致。"""

    def __init__(self, database, user: dict | None, case_id: str) -> None:
        self.database = database
        self.user = user
        self.case_id = case_id
        self._readable: dict[tuple, bool] = {}

    def readable(self, raw: object) -> bool:
        ref = self._validated(raw)
        if ref is None:
            return False
        if ref.identity() not in self._readable:
            self._readable[ref.identity()] = source_readable(
                self.database, self.user, self.case_id, ref
            )
        return self._readable[ref.identity()]

    def _validated(self, raw: object) -> SourceRef | None:
        if isinstance(raw, SourceRef):
            return raw
        try:
            return SourceRef.model_validate(raw)
        except ValidationError:
            return None


def visible_snapshot(database, snapshot: AgentSnapshot, user: dict) -> AgentSnapshot:
    gate = SourceGate(database, user, snapshot.case_id)
    messages = [_visible_message(gate, message) for message in snapshot.messages]
    artifacts = [_visible_artifact(gate, artifact) for artifact in snapshot.artifacts]
    return snapshot.model_copy(update={"messages": messages, "artifacts": artifacts})


def visible_parts(gate: SourceGate, parts: list[dict]) -> list[dict]:
    """助手消息引用的任一来源不可读时隐藏正文文本，工具输出逐项遮蔽。"""
    tainted = any(not gate.readable(ref) for ref in _message_refs(parts))
    return [_visible_part(gate, part, tainted) for part in parts]


def parts_projector(database, user: dict | None, case_id: str):
    """注入恢复流与模型历史的投影函数；每次调用重建 SourceGate 逐消息复验。"""

    def project(parts: list[dict]) -> list[dict]:
        return visible_parts(SourceGate(database, user, case_id), parts)

    return project


def _visible_message(gate: SourceGate, message: AgentMessage) -> AgentMessage:
    if message.role != "assistant":
        return message
    return message.model_copy(update={"parts": visible_parts(gate, message.parts)})


def _visible_artifact(gate: SourceGate, artifact: AgentArtifact) -> AgentArtifact:
    readable = [gate.readable(ref) for ref in artifact.sources]
    sources = [ref for ref, ok in zip(artifact.sources, readable) if ok]
    if all(readable):
        return artifact
    return artifact.model_copy(update={
        "sources": sources,
        "replacement": HIDDEN_REVISION,
        "reason": HIDDEN_REVISION,
    })


def _visible_part(gate: SourceGate, part: dict, tainted: bool) -> dict:
    kind = part.get("type")
    if kind in ("text", "reasoning"):
        return _text_part(part, tainted)
    if kind == "tool-read_source":
        return _read_part(gate, part)
    if kind == "tool-search_corpus":
        return _search_part(gate, part)
    if kind == "tool-propose_revision":
        return _propose_part(part, tainted)
    return part


def _text_part(part: dict, tainted: bool) -> dict:
    if not tainted:
        return part
    hidden = {"type": part.get("type") or "text", "text": HIDDEN_ANSWER}
    if part.get("id"):
        hidden["id"] = part["id"]
    return hidden


def _propose_part(part: dict, tainted: bool) -> dict:
    """修订提议的工具输入/输出复述受限来源内容时一并遮蔽，仅留结构字段。"""
    if not tainted:
        return part
    return {
        **part,
        "input": _revision_view(part.get("input")),
        "output": _revision_view(part.get("output")),
    }


def _revision_view(raw: object) -> object:
    if not isinstance(raw, dict):
        return raw
    hidden = dict(raw)
    for field in ("replacement", "reason"):
        if field in hidden:
            hidden[field] = HIDDEN_REVISION
    return hidden


def _read_part(gate: SourceGate, part: dict) -> dict:
    output = part.get("output")
    ref = output.get("usedSourceRef") if isinstance(output, dict) else None
    if not ref or gate.readable(ref):
        return part
    return {**part, "output": dict(NO_ACCESS_OUTPUT)}


def _search_part(gate: SourceGate, part: dict) -> dict:
    output = part.get("output")
    if not isinstance(output, dict):
        return part
    sources = [ref for ref in output.get("sources", []) if gate.readable(ref)]
    return {**part, "output": {**output, "sources": sources}}


def _message_refs(parts: list[dict]) -> list[object]:
    refs: list[object] = []
    for part in parts:
        refs.extend(_part_refs(part))
    return refs


def _part_refs(part: dict) -> list[object]:
    output = part.get("output")
    if not isinstance(output, dict):
        return []
    if part.get("type") == "tool-read_source":
        return [output["usedSourceRef"]] if output.get("usedSourceRef") else []
    if part.get("type") == "tool-search_corpus":
        return list(output.get("sources") or [])
    return []
