"""Skill 包测试夹具：标准 ZIP 与未标记 UTF-8 文件名的手工构造 ZIP。

结构复刻真实 v2.1 包：单一 SKILL.md 入口 + references 中文模板与范例 +
中文命名附加文件；未标记变体用于证明 metadata_encoding 兜底路径。
"""

from __future__ import annotations

import struct
import zipfile
from io import BytesIO

SKILL_DIR = "sizheng-case-generator"
SKILL_ID = "sizheng-case-generator"
TEMPLATE_PATH = "references/模板规范_v2.0.md"
EXAMPLE_PATH = "references/examples/生态保护案例-本科生教学设计.txt"
INSTALL_PATH = "安装说明.txt"

SKILL_MD = """---
name: "sizheng-case-generator"
description: "习近平文化思想课程思政案例生成技能。当用户需要为《习近平文化思想》备课、生成思政教学案例（案例文本+教学设计）、按本研双版本撰写案例时使用。完整模板规范与范例见 references/ 目录。"
---

# 习近平文化思想课程思政案例生成技能

为《习近平文化思想》课程生成配套思政案例，交付案例文本 + 教学设计。

详细规范（选题原则、结构模块、行文风格、格式、检查清单、检索策略）见 `references/模板规范_v2.0.md`，写作前必读。

## 范例文件（references/examples/）

写作前至少通读一个范例：`references/examples/生态保护案例-本科生教学设计.txt`
"""

TEMPLATE_TEXT = "# 模板规范 v2.0\n\n选题原则、结构模块、行文风格、检查清单。"
EXAMPLE_TEXT = "教学设计范例：主题——生态保护与生物多样性。"
INSTALL_TEXT = "将本目录复制到 Agent 的 skills 目录即可。"

FILES = {
    f"{SKILL_DIR}/SKILL.md": SKILL_MD,
    f"{SKILL_DIR}/{TEMPLATE_PATH}": TEMPLATE_TEXT,
    f"{SKILL_DIR}/{EXAMPLE_PATH}": EXAMPLE_TEXT,
    f"{SKILL_DIR}/{INSTALL_PATH}": INSTALL_TEXT,
}


def build_package(files: dict[str, str] | None = None) -> bytes:
    """标准包：非 ASCII 文件名由 zipfile 自动标记 UTF-8 标志位。"""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, text in (files or FILES).items():
            archive.writestr(path, text)
    return buffer.getvalue()


def _local_entry(name: bytes, data: bytes) -> bytes:
    crc = zlib_crc(data)
    header = struct.pack(
        "<IHHHHHIIIHH", 0x04034B50, 20, 0, 0, 0, 0, crc, len(data), len(data),
        len(name), 0,
    )
    return header + name + data


def _central_entry(name: bytes, data: bytes, offset: int) -> bytes:
    header = struct.pack(
        "<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0, 0, 0, 0, zlib_crc(data),
        len(data), len(data), len(name), 0, 0, 0, 0, 0, offset,
    )
    return header + name


def build_unflagged_package() -> bytes:
    """手工构造 ZIP：UTF-8 文件名字节，但清除 0x800 标志（常见 Windows 工具产物）。"""
    locals_: list[bytes] = []
    centrals: list[bytes] = []
    offset = 0
    for path, text in FILES.items():
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


def zlib_crc(data: bytes) -> int:
    import zlib

    return zlib.crc32(data) & 0xFFFFFFFF
