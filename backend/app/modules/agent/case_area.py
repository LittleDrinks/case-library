"""资料区领域服务：服务端真源构建保留来源清单，校验消息中的来源选区。

条目身份与统一来源 API 一致：案例来源用挂载 id（同一案例的 v1/v2 各自
成条），素材用素材 ID，附件用附件 ID。浏览器提交的名称、版本或描述
一律不采信，真实来源案例与已批准版本由服务端解析。可选 case_version_id
把清单固定到某个已发布/快照版本，供只读工作台集成使用。
"""

from __future__ import annotations

from pymongo.database import Database

from app.modules.agent.models import SourceRef
from app.modules.cases.service import CaseError
from app.modules.cases.sources import SOURCE_COLLECTIONS

SOURCE_TYPES = tuple(SOURCE_COLLECTIONS)
VIEW_FIELDS = (
    ("kind", "kind"), ("id", "id"), ("title", "title"), ("snippet", "snippet"),
    ("version", "version"), ("version_id", "versionId"), ("locator", "locator"),
)


def area_rows(database: Database, case_id: str,
              version_id: str | None = None) -> dict[str, list[dict]]:
    """资料区三类原始行：活动草稿取活集合，指定版本取冻结嵌入行。"""
    if version_id:
        return _frozen_rows(database, case_id, version_id)
    return {
        "attachment": list(database.attachments.find({"caseId": case_id}).sort("createdAt", 1)),
        "material": list(database.case_materials.find({"caseId": case_id}).sort("materialId", 1)),
        "case": list(database.case_sources.find({"caseId": case_id}).sort("id", 1)),
    }


def _frozen_rows(database: Database, case_id: str, version_id: str) -> dict[str, list[dict]]:
    version = database.case_versions.find_one({"id": version_id, "caseId": case_id})
    version = version or database.case_snapshots.find_one({"id": version_id, "caseId": case_id})
    if not version:
        raise CaseError(404, "案例版本不存在")
    return {
        "attachment": list(version.get("attachments", [])),
        "material": list(version.get("materials", [])),
        "case": list(version.get("caseSources", [])),
    }


def retained_sources(database: Database, case_id: str,
                     version_id: str | None = None) -> list[SourceRef]:
    """当前案例资料区的服务端来源清单：顺序稳定、含稳定 ID 与内容定位。"""
    rows = area_rows(database, case_id, version_id)
    return [
        *_attachment_refs(case_id, rows["attachment"]),
        *_material_refs(rows["material"]),
        *_case_refs(rows["case"]),
    ]


def _attachment_refs(case_id: str, rows: list[dict]) -> list[SourceRef]:
    return [
        SourceRef(
            kind="attachment", id=row["id"], title=row.get("name") or "",
            locator=f"attachment:{case_id}/{row['id']}",
        )
        for row in rows
    ]


def _material_refs(rows: list[dict]) -> list[SourceRef]:
    return [
        SourceRef(
            kind="material", id=_material_id(row), title=row.get("title") or "",
            locator=f"material:{_material_id(row)}",
        )
        for row in rows
    ]


def _case_refs(rows: list[dict]) -> list[SourceRef]:
    return [
        SourceRef(
            kind="case", id=row["id"], title=row.get("title") or "",
            version=f"v{row['versionNumber']}", version_id=row["versionId"],
            locator=f"case:{row['sourceCaseId']}@{row['versionId']}",
        )
        for row in rows
    ]


def _material_id(row: dict) -> str:
    return row.get("materialId") or row["id"]


def selection_from_parts(database: Database, case_id: str, parts: list[dict],
                         version_id: str | None = None) -> list[dict]:
    """解析消息 data-source 部分：稳定有序，逐项对照资料区校验。"""
    selected = []
    for part in parts:
        if part.get("type") != "data-source":
            continue
        ref = _resolve_selected(database, case_id, part.get("data"), version_id)
        selected.append({"sourceType": ref.kind, "id": ref.id})
    return selected


def _resolve_selected(database: Database, case_id: str, data: object,
                      version_id: str | None) -> SourceRef:
    if not isinstance(data, dict):
        raise CaseError(422, "来源选区格式无效")
    kind, source_id = data.get("sourceType"), data.get("id")
    if kind not in SOURCE_TYPES or not isinstance(source_id, str) or not source_id:
        raise CaseError(422, "来源选区格式无效")
    ref = find_ref(retained_sources(database, case_id, version_id), str(kind), source_id)
    if ref is None:
        raise CaseError(422, "所选来源不在当前案例资料区")
    return ref


def find_ref(refs: list[SourceRef], kind: str, source_id: str) -> SourceRef | None:
    """按稳定类型 + 条目 ID 查找；版本身份由服务端解析，不从标题推断。"""
    return next((ref for ref in refs if ref.kind == kind and ref.id == source_id), None)


def dedupe_refs(refs: list[SourceRef]) -> list[SourceRef]:
    """按类型 + 条目 ID + 实际版本去重，保留首次出现；选择不被检索覆盖。"""
    seen: set[tuple[str, str, str]] = set()
    kept = []
    for ref in refs:
        if ref.identity() in seen:
            continue
        seen.add(ref.identity())
        kept.append(ref)
    return kept


def ref_view(ref: SourceRef) -> dict:
    return {alias: getattr(ref, name) for name, alias in VIEW_FIELDS}


def catalog_instructions(title: str, refs: list[SourceRef], selected: list[dict],
                         selections: list[dict]) -> str:
    """Run 级指令：资料区清单、本条消息点选来源与正文选区。"""
    lines = [f"## 当前案例资料区（{title}）", "教师已保留的来源，按需用 read_source 读取："]
    lines += [_catalog_line(index, ref) for index, ref in enumerate(refs, start=1)]
    if not refs:
        lines.append("（资料区当前为空）")
    names = ", ".join(str(item["id"]) for item in selected) or "无"
    lines += ["", f"本条消息教师点选的来源：{names}", _selection_lines(selections)]
    return "\n".join(lines)


def _catalog_line(index: int, ref: SourceRef) -> str:
    return (
        f"{index}. [{ref.kind}] {ref.title}（id: {ref.id}，"
        f"版本: {ref.version or '未固定'}）"
    )


def _selection_lines(selections: list[dict]) -> str:
    if not selections:
        return "本条消息教师选中的正文段落：无"
    rows = [f"第 {item['paragraphIndex'] + 1} 段（{item['quote']}）" for item in selections]
    return f"本条消息教师选中的正文段落：{'；'.join(rows)}"
