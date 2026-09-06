"""Skill 包解析器定向测试：元数据、非法路径、重复成员与中文资源。

只覆盖 app.modules.skills.parse 的公共接口，不依赖数据库、对象存储或 HTTP 路由。
"""

from __future__ import annotations

import io
import struct
import zipfile
import zlib

import pytest

from app.modules.skills.parse import (
    ENTRY_NAME,
    MAX_PACKAGE_FILES,
    MAX_TOTAL_UNCOMPRESSED_BYTES,
    SkillPackageError,
    open_package,
    parse_package,
)

ENTRY_DIR = "sizheng-case-generator"
TEMPLATE_PATH = "references/模板规范_v2.0.md"
EXAMPLE_PATH = "references/examples/生态保护案例-本科生教学设计.txt"
INSTALL_PATH = "安装说明.txt"
INSTALL_TEXT = "将本目录复制到 Agent 的 skills 目录即可。"
EXAMPLE_TEXT = "教学设计范例：主题——生态保护与生物多样性。"

SKILL_MD = """---
name: "sizheng-case-generator"
description: "习近平文化思想课程思政案例生成技能。"
---

# 习近平文化思想课程思政案例生成技能

详细规范见 `references/模板规范_v2.0.md`，范例见 examples 目录。
"""


def build_package(files: dict[str, str]) -> bytes:
    """标准 ZIP：非 ASCII 文件名由 zipfile 自动标记 UTF-8 标志位。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, text in files.items():
            archive.writestr(path, text)
    return buffer.getvalue()


def base_files(entry: str = f"{ENTRY_DIR}/{ENTRY_NAME}") -> dict[str, str]:
    files = {entry: SKILL_MD, f"{ENTRY_DIR}/{TEMPLATE_PATH}": "# 模板规范 v2.0"}
    files[f"{ENTRY_DIR}/{INSTALL_PATH}"] = INSTALL_TEXT
    return files


def expect_error(data: bytes, expected: str) -> None:
    with pytest.raises(SkillPackageError) as excinfo:
        parse_package(data)
    assert excinfo.value.status_code == 422
    assert expected in excinfo.value.detail


def test_parses_metadata_manifest_and_single_entry() -> None:
    package = parse_package(build_package(base_files()))
    assert (package.name, package.root) == ("sizheng-case-generator", ENTRY_DIR)
    assert package.description == "习近平文化思想课程思政案例生成技能。"
    assert package.entry_path == f"{ENTRY_DIR}/{ENTRY_NAME}"
    assert package.body.startswith("# 习近平文化思想课程思政案例生成技能")
    assert {row.path for row in package.files} == {TEMPLATE_PATH, INSTALL_PATH}
    assert all(len(row.sha256) == 64 for row in package.files)


def test_accepts_entry_at_zip_root() -> None:
    files = {"SKILL.md": SKILL_MD, TEMPLATE_PATH: "# 模板规范 v2.0"}
    package = parse_package(build_package(files))
    assert (package.root, package.entry_path) == ("", "SKILL.md")
    assert [row.path for row in package.files] == [TEMPLATE_PATH]


def test_rejects_missing_and_multiple_entries() -> None:
    expect_error(build_package({"a/b/SKILL.md": SKILL_MD}), "包内缺少 SKILL.md 入口文件")
    expect_error(build_package(base_files() | {"SKILL.md": SKILL_MD}), "包内包含多个 SKILL.md 入口")
    expect_error(build_package(base_files() | {"other/SKILL.md": SKILL_MD}), "包内包含多个 SKILL.md 入口")


def test_not_a_zip_is_rejected() -> None:
    expect_error(b"not a zip", "不是有效的 ZIP 文件")


@pytest.mark.parametrize("bad_entry", [
    "../SKILL.md",
    "/SKILL.md",
    ".hidden/SKILL.md",
    "./SKILL.md",
])
def test_rejects_unsafe_entry_paths(bad_entry: str) -> None:
    """入口路径沿用同一安全校验：..、绝对路径、点目录、非常规化写法都拒绝。"""
    expect_error(build_package({bad_entry: SKILL_MD}), "不安全的资源路径")


def raw_skill_md(raw: str) -> str:
    body = SKILL_MD.split("---\n", 2)[-1]
    return f"---\n{raw}\n---{body}"


GOOD_NAME = 'name: "sizheng-case-generator"'
GOOD_DESCRIPTION = 'description: "简要描述"'


@pytest.mark.parametrize("raw,expected", [
    (f"name: 123\n{GOOD_DESCRIPTION}", "name 必须是字符串，收到数字"),
    (f"name: true\n{GOOD_DESCRIPTION}", "name 必须是字符串，收到布尔值"),
    (f"name: [a-b]\n{GOOD_DESCRIPTION}", "name 必须是字符串，收到列表"),
    (f"{GOOD_NAME}\ndescription: 20240901", "description 必须是字符串，收到数字"),
    (f"{GOOD_NAME}\ndescription: {{zh: 简介}}", "description 必须是字符串，收到对象"),
    (f'name: "   "\n{GOOD_DESCRIPTION}', "缺少非空 name"),
    (f'{GOOD_NAME}\ndescription: "\\n \\t"', "缺少非空 description"),
    (f'name: "Sizheng Case"\n{GOOD_DESCRIPTION}', "name 只能包含"),
    (f'name: "{"a" * 65}"\n{GOOD_DESCRIPTION}', "name 长度须为"),
    (f'{GOOD_NAME}\ndescription: "{"长" * 1025}"', "description 不能超过"),
])
def test_rejects_invalid_metadata(raw: str, expected: str) -> None:
    entry = f"{ENTRY_DIR}/{ENTRY_NAME}"
    expect_error(build_package({entry: raw_skill_md(raw)}), expected)


@pytest.mark.parametrize("bad", [
    "../evil.txt",
    "sub/../../evil.txt",
    "windows\\path.txt",
    ".hidden/secret.txt",
    "/etc/evil.txt",
])
def test_rejects_unsafe_resource_paths(bad: str) -> None:
    expect_error(build_package({"SKILL.md": SKILL_MD, bad: "evil"}), "不安全的资源路径")


def test_rejects_duplicate_members() -> None:
    """ZIP 允许同名成员：清单记首个、按名读取命中末个，必须整体拒绝。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{ENTRY_DIR}/{ENTRY_NAME}", SKILL_MD)
        archive.writestr(f"{ENTRY_DIR}/{TEMPLATE_PATH}", "# 首个内容")
        archive.writestr(f"{ENTRY_DIR}/{TEMPLATE_PATH}", "# 后写入的同名内容")
    expect_error(buffer.getvalue(), f"重复资源路径：{TEMPLATE_PATH}")


def test_reads_chinese_resource_content_exactly() -> None:
    files = base_files() | {f"{ENTRY_DIR}/{EXAMPLE_PATH}": EXAMPLE_TEXT}
    data = build_package(files)
    package = parse_package(data)
    assert {row.path for row in package.files} >= {EXAMPLE_PATH}
    assert next(row.size for row in package.files if row.path == EXAMPLE_PATH) == len(
        EXAMPLE_TEXT.encode("utf-8")
    )
    with open_package(data) as archive:
        assert archive.read(f"{ENTRY_DIR}/{EXAMPLE_PATH}").decode("utf-8") == EXAMPLE_TEXT
        assert archive.read(f"{ENTRY_DIR}/{INSTALL_PATH}").decode("utf-8") == INSTALL_TEXT


def _local_entry(name: bytes, data: bytes, declared: int | None = None) -> bytes:
    size = declared if declared is not None else len(data)
    header = struct.pack(
        "<IHHHHHIIIHH", 0x04034B50, 20, 0, 0, 0, 0, zlib.crc32(data) & 0xFFFFFFFF,
        size, size, len(name), 0,
    )
    return header + name + data


def _central_entry(
    name: bytes, data: bytes, offset: int, declared: int | None = None,
) -> bytes:
    size = declared if declared is not None else len(data)
    header = struct.pack(
        "<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0, 0, 0, 0,
        zlib.crc32(data) & 0xFFFFFFFF, size, size, len(name),
        0, 0, 0, 0, 0, offset,
    )
    return header + name


def build_lying_size_package(declared: int) -> bytes:
    """手工 ZIP：成员声明解压大小远超实际字节，用于证明计量先于内容读取。"""
    name = f"{ENTRY_DIR}/{ENTRY_NAME}".encode("utf-8")
    data = b"\xff\x00 binary garbage"
    local = _local_entry(name, data, declared)
    central = _central_entry(name, data, 0, declared)
    eocd = struct.pack(
        "<IHHHHIIH", 0x06054B50, 0, 0, 1, 1, len(central), len(local), 0,
    )
    return local + central + eocd


def build_unflagged_package(files: dict[str, str]) -> bytes:
    """手工构造 ZIP：UTF-8 文件名字节但清除 0x800 标志（常见 Windows 工具产物）。"""
    locals_: list[bytes] = []
    centrals: list[bytes] = []
    offset = 0
    for path, text in files.items():
        name, data = path.encode("utf-8"), text.encode("utf-8")
        entry = _local_entry(name, data)
        locals_.append(entry)
        centrals.append(_central_entry(name, data, offset))
        offset += len(entry)
    directory = b"".join(centrals)
    eocd = struct.pack(
        "<IHHHHIIH", 0x06054B50, 0, 0, len(centrals), len(centrals),
        len(directory), offset, 0,
    )
    return b"".join(locals_) + directory + eocd


def test_unflagged_utf8_names_read_chinese_paths_exactly() -> None:
    files = base_files() | {f"{ENTRY_DIR}/{EXAMPLE_PATH}": EXAMPLE_TEXT}
    data = build_unflagged_package(files)
    package = parse_package(data)
    assert {row.path for row in package.files} >= {EXAMPLE_PATH, INSTALL_PATH}
    with open_package(data) as archive:
        assert archive.read(f"{ENTRY_DIR}/{EXAMPLE_PATH}").decode("utf-8") == EXAMPLE_TEXT


def test_entry_body_counts_toward_total_before_read() -> None:
    """入口正文计入解压总量且在读取前拒绝：实际字节非法，先读必报不是文本文件。"""
    declared = MAX_TOTAL_UNCOMPRESSED_BYTES + 1
    expect_error(build_lying_size_package(declared), "解压后总大小")


def test_file_count_limit_rejected_before_read() -> None:
    """入口计入数量限制：入口加 1000 个资源共 1001 个成员，在任何读取前拒绝。"""
    files = base_files()
    for index in range(MAX_PACKAGE_FILES):
        files[f"{ENTRY_DIR}/bulk/成员{index}.txt"] = "内容"
    expect_error(build_package(files), "包内文件数量不能超过")
