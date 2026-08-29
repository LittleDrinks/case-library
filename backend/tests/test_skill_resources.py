from __future__ import annotations

import hashlib
import re
from pathlib import Path


RESOURCE_ROOT = (
    Path(__file__).parents[1]
    / "app/modules/skills/resources/sizheng-case-generator/v2.1"
)
MANIFEST = RESOURCE_ROOT / "MANIFEST.md"
EXPECTED_RUNTIME_ID = "sizheng-case-generator.v2.1.m1"
ROW = re.compile(
    r"^\| `(?P<id>[^`]+)` \| `(?P<role>[^`]+)` \| `(?P<path>[^`]+)` \| "
    r"`(?P<loadable>true|false)` \| `(?P<sha256>[0-9a-f]{64})` \|$"
)


def manifest_rows() -> list[dict[str, str]]:
    lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    table_lines = [line for line in lines if line.startswith("| `")]
    rows = []
    for line in table_lines:
        match = ROW.fullmatch(line)
        assert match, f"invalid manifest row: {line}"
        rows.append(match.groupdict())
    return rows


def resource_files() -> set[str]:
    return {
        str(path.relative_to(RESOURCE_ROOT))
        for path in RESOURCE_ROOT.rglob("*")
        if path.is_file() and path != MANIFEST
    }


def test_skill_v21_manifest_declares_all_utf8_markdown_resources() -> None:
    rows = manifest_rows()
    assert len(rows) == 17
    assert len({row["id"] for row in rows}) == len(rows)
    declared = {row["path"] for row in rows}
    actual = resource_files()
    assert declared == actual
    assert all(Path(name).suffix == ".md" for name in actual)
    assert not any(Path(name).suffix.lower() == ".zip" for name in actual)
    for row in rows:
        path = RESOURCE_ROOT / row["path"]
        content = path.read_bytes()
        content.decode("utf-8")
        assert hashlib.sha256(content).hexdigest() == row["sha256"]


def test_only_m1_runtime_skill_is_loadable() -> None:
    rows = manifest_rows()
    loadable = {row["id"] for row in rows if row["loadable"] == "true"}
    assert loadable == {EXPECTED_RUNTIME_ID}
    assert sum(row["role"] == "runtime-skill" for row in rows) == 1
    non_runtime = [row for row in rows if row["id"] != EXPECTED_RUNTIME_ID]
    assert all(
        row["loadable"] == "false"
        and row["path"].startswith("references/")
        and row["role"] in {"source-reference", "reference", "reference-example"}
        for row in non_runtime
    )
    runtime = next(row for row in rows if row["id"] == EXPECTED_RUNTIME_ID)
    assert runtime["role"] == "runtime-skill"
    assert runtime["path"] == "SKILL.md"


def test_m1_runtime_skill_exposes_its_public_rules() -> None:
    content = (RESOURCE_ROOT / "SKILL.md").read_text(encoding="utf-8")
    required = (
        f'id: "{EXPECTED_RUNTIME_ID}"',
        "教师明确启用",
        "topic",
        "angle",
        "audience",
        "search_corpus",
        "propose_revision",
        "教师明确确认",
        "web_search",
        "七阶段",
        "双版本",
        "DOCX",
        "脚本",
    )
    assert all(token in content for token in required)


def test_skill_v21_manifest_pins_source_archive() -> None:
    content = MANIFEST.read_text(encoding="utf-8")
    expected = "15479fd46995e9c13a05de822e93d35c31c5003eb5d741b3b8a510988063e542"
    assert f'source_sha256: "{expected}"' in content
