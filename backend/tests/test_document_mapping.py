from copy import deepcopy

import pytest

from app.modules.agent import prosemirror
from app.modules.annotations.service import document_mapping
from app.modules.cases.service import CaseError


def test_empty_content_representation_preserves_native_mapping():
    original = {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "原文"}]},
        {"type": "paragraph", "content": []},
    ]}
    updated, steps = prosemirror.replaced_document_with_steps(original, 1, 3, "原文", "修改")
    updated["content"][1]["content"] = []
    mapping = document_mapping(original, updated, steps)
    assert mapping.map(1) == 1


@pytest.mark.parametrize("change", ["text", "format", "citation", "paragraph"])
def test_mapping_still_rejects_real_document_differences(change):
    original = {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "原文"}]},
        {"type": "paragraph", "content": []},
    ]}
    updated, steps = prosemirror.replaced_document_with_steps(original, 1, 3, "原文", "修改")
    changed = deepcopy(updated)
    text = changed["content"][0]["content"][0]
    if change == "text":
        text["text"] = "不同"
    elif change == "format":
        text["marks"] = [{"type": "bold"}]
    elif change == "citation":
        text["marks"] = [{"type": "citation", "attrs": {"sourceType": "material", "sourceId": "other"}}]
    else:
        changed["content"].pop()
    with pytest.raises(CaseError, match="正文变更与位置映射不一致"):
        document_mapping(original, changed, steps)
