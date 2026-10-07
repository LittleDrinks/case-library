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
    merge_source_refs,
)
from app.modules.agent.source_reader import source_metadata_readable, source_readable
from app.modules.auth.sessions import load_current_user

HIDDEN_ANSWER = "该回答引用的来源当前不可读，相关内容已隐藏"
HIDDEN_REVISION = "该候选引用的来源当前不可读，修订内容已隐藏"
HIDDEN_BLOCKS = [{"type": "paragraph", "text": HIDDEN_REVISION}]
NO_ACCESS_OUTPUT = {"status": "no_access", "detail": "来源当前不可读"}
SOURCE_DEPENDENCIES = "_sourceDependencies"


class SourceGate:
    """同一读取轮内按来源身份缓存可读性，保证各输出面投影口径一致。"""

    def __init__(
        self, database, user: dict | None, case_id: str, version_id: str | None = None,
    ) -> None:
        self.database = database
        self._authenticated = user is not None
        self.user = load_current_user(database, user)
        self.case_id = case_id
        self.version_id = version_id
        self._readable: dict[tuple, bool] = {}

    def readable(self, raw: object) -> bool:
        ref = self._validated(raw)
        if ref is None:
            return False
        if self._authenticated and self.user is None:
            return False
        if ref.content_available is False:
            return source_metadata_readable(self.database, self.user, ref)
        if ref.identity() not in self._readable:
            self._readable[ref.identity()] = source_readable(
                self.database, self.user, self.case_id, ref, self.version_id
            )
        return self._readable[ref.identity()]

    def _validated(self, raw: object) -> SourceRef | None:
        if isinstance(raw, SourceRef):
            return raw
        try:
            return SourceRef.model_validate(raw)
        except ValidationError:
            return None


def visible_snapshot(
    database, snapshot: AgentSnapshot, user: dict, version_id: str | None = None,
) -> AgentSnapshot:
    gate = SourceGate(database, user, snapshot.case_id, version_id)
    messages = [_visible_message(gate, message) for message in snapshot.messages]
    artifacts = [_visible_artifact(gate, artifact) for artifact in snapshot.artifacts]
    return snapshot.model_copy(update={"messages": messages, "artifacts": artifacts})


def visible_artifact(database, artifact: AgentArtifact, user: dict) -> AgentArtifact:
    return _visible_artifact(SourceGate(database, user, artifact.case_id), artifact)


def visible_parts(
    gate: SourceGate, parts: list[dict], metadata: dict | None = None,
) -> list[dict]:
    """助手消息引用的任一来源不可读时隐藏正文文本，工具输出逐项遮蔽。"""
    tainted = any(not gate.readable(ref) for ref in _message_refs(parts, metadata))
    return [_visible_part(gate, part, tainted) for part in parts]


def parts_projector(
    database, user: dict | None, case_id: str, version_id: str | None = None,
    dependencies: list[SourceRef] | None = None,
):
    """注入恢复流与模型历史的投影函数；每次调用重建 SourceGate 逐消息复验。"""

    def project(parts: list[dict], metadata: dict | None = None) -> list[dict]:
        gate = SourceGate(database, user, case_id, version_id)
        refs = _message_refs(parts, metadata)
        if dependencies is not None:
            for raw in refs:
                ref = gate._validated(raw)
                if ref is None or not gate.readable(ref):
                    continue
                dependencies[:] = merge_source_refs([*dependencies, ref])
        return visible_parts(gate, parts, metadata)

    return project


def _visible_message(gate: SourceGate, message: AgentMessage) -> AgentMessage:
    if message.role != "assistant":
        return message.model_copy(update={"metadata": public_metadata(message.metadata)})
    return message.model_copy(update={
        "metadata": public_metadata(message.metadata),
        "parts": visible_parts(gate, message.parts, message.metadata),
    })


def public_metadata(metadata: dict | None) -> dict:
    return {key: value for key, value in (metadata or {}).items() if key != SOURCE_DEPENDENCIES}


def _visible_artifact(gate: SourceGate, artifact: AgentArtifact) -> AgentArtifact:
    readable = [gate.readable(ref) for ref in artifact.sources]
    sources = [ref for ref, ok in zip(artifact.sources, readable) if ok]
    if all(readable):
        return artifact
    hidden = {
        "sources": sources,
        "replacement": HIDDEN_REVISION,
        "reason": HIDDEN_REVISION,
    }
    if artifact.kind == "document":
        hidden["blocks"] = list(HIDDEN_BLOCKS)
    return artifact.model_copy(update=hidden)


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
    if kind in ("tool-write_document", "tool-propose_document"):
        return _write_part(part, tainted)
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


def _write_part(part: dict, tainted: bool) -> dict:
    """整篇写入/提议的工具输入复述受限来源内容时遮蔽块文本与摘要。"""
    if not tainted:
        return part
    return {**part, "input": _write_input_view(part.get("input"))}


def _write_input_view(raw: object) -> object:
    if not isinstance(raw, dict):
        return raw
    hidden = dict(raw)
    for field in ("summary", "reason"):
        if field in hidden:
            hidden[field] = HIDDEN_REVISION
    if "blocks" in hidden:
        hidden["blocks"] = list(HIDDEN_BLOCKS)
    return hidden


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


def _message_refs(parts: list[dict], metadata: dict | None = None) -> list[object]:
    refs: list[object] = []
    dependencies = (metadata or {}).get(SOURCE_DEPENDENCIES, [])
    if isinstance(dependencies, list):
        refs.extend(dependencies)
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
