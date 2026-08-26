from __future__ import annotations

from dataclasses import dataclass

STAGES = (
    {"id": "grad", "name": "硕博公共思政"},
    {"id": "ug", "name": "本科思政"},
    {"id": "embed", "name": "专业课程思政"},
)
CASE_TYPES = (
    {
        "id": "ct-general",
        "name": "通用案例",
        "description": "适用于不依赖特定叙事结构的教学主题",
    },
    {
        "id": "ct-policy",
        "name": "政策落实类",
        "description": "分析政策从目标到落地的过程与成效",
    },
    {
        "id": "ct-figure",
        "name": "人物传记类",
        "description": "以人物经历和关键选择呈现价值引领",
    },
    {
        "id": "ct-thought",
        "name": "思想实验类",
        "description": "用假设情境和矛盾冲突组织讨论",
    },
    {
        "id": "ct-school",
        "name": "校本实践类",
        "description": "提炼校本育人实践的做法与经验",
    },
    {
        "id": "ct-tech",
        "name": "科技创新与科技报国类",
        "description": "连接科技创新实践与科技报国使命",
    },
    {
        "id": "ct-society",
        "name": "社会热点与治理类",
        "description": "围绕现实议题分析治理选择与边界",
    },
)
ALL_STAGE_IDS = tuple(stage["id"] for stage in STAGES)
ALL_CASE_TYPE_IDS = tuple(case_type["id"] for case_type in CASE_TYPES)
TEMPLATES = (
    {
        "id": "tpl-general-v1",
        "version": 1,
        "name": "通用案例结构",
        "stageIds": ALL_STAGE_IDS,
        "typeIds": ALL_CASE_TYPE_IDS,
        "sections": (
            {"level": 2, "title": "（一）建设目标"},
            {"level": 2, "title": "（二）主要内容设计"},
            {"level": 2, "title": "（三）方法与策略"},
            {"level": 2, "title": "（四）评价与成效"},
            {"level": 2, "title": "（五）特色与创新"},
        ),
        "enabled": True,
    },
    {
        "id": "tpl-teaching-standard-v1",
        "version": 1,
        "name": "教学案例标准版",
        "stageIds": ALL_STAGE_IDS,
        "typeIds": ALL_CASE_TYPE_IDS,
        "sections": (
            {"level": 1, "title": "一、教学说明（800字左右）"},
            {"level": 2, "title": "（一）教学目的"},
            {"level": 2, "title": "（二）阅读思考题（2～3个）"},
            {"level": 2, "title": "（三）教学安排"},
            {"level": 2, "title": "（四）注意事项"},
            {"level": 1, "title": "二、文本内容（2500字左右）"},
            {"level": 1, "title": "三、附件"},
        ),
        "enabled": True,
    },
)


@dataclass(frozen=True)
class CaseCreation:
    stage: dict
    case_type: dict
    template: dict


def case_creation_catalog() -> dict:
    return {
        "stages": [dict(stage) for stage in STAGES],
        "caseTypes": [dict(case_type) for case_type in CASE_TYPES],
        "templates": [
            _catalog_template(template) for template in TEMPLATES if template["enabled"]
        ],
    }


def _catalog_template(template: dict) -> dict:
    return {
        "id": template["id"],
        "version": template["version"],
        "name": template["name"],
        "stageIds": list(template["stageIds"]),
        "typeIds": list(template["typeIds"]),
        "sectionTitles": [section["title"] for section in template["sections"]],
    }


def resolve_case_creation(
    stage_id: str, type_id: str, template_id: str
) -> CaseCreation | None:
    stage = _record(STAGES, stage_id)
    case_type = _record(CASE_TYPES, type_id)
    template = _record(TEMPLATES, template_id)
    if not stage or not case_type or not _template_matches(template, stage_id, type_id):
        return None
    return CaseCreation(stage, case_type, template)


def _record(records: tuple[dict, ...], record_id: str) -> dict | None:
    return next((record for record in records if record["id"] == record_id), None)


def _template_matches(template: dict | None, stage_id: str, type_id: str) -> bool:
    return bool(
        template
        and template["enabled"]
        and stage_id in template["stageIds"]
        and type_id in template["typeIds"]
    )


def new_case_document(template: dict) -> dict:
    return {
        "type": "doc",
        "content": [
            node for section in template["sections"] for node in _section_nodes(section)
        ],
    }


def _section_nodes(section: dict) -> list[dict]:
    heading = {
        "type": "heading",
        "attrs": {"level": section["level"]},
        "content": [{"type": "text", "text": section["title"]}],
    }
    return [heading, {"type": "paragraph", "content": []}]


def creation_metadata(creation: CaseCreation) -> dict:
    return {
        "audience": creation.stage["id"],
        "stageText": creation.stage["name"],
        "typeId": creation.case_type["id"],
        "typeName": creation.case_type["name"],
        "templateId": creation.template["id"],
        "templateVersion": creation.template["version"],
        "templateName": creation.template["name"],
    }
