"""Skill 包解析：成熟 ZIP 读取 + SKILL.md frontmatter 校验，全部文件按惰性数据处理。

包内不执行任何脚本；资源引用关系是数据，仅记录路径供按需读取。
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

import frontmatter

MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_PACKAGE_FILES = 1000
MAX_TOTAL_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
ENTRY_NAME = "SKILL.md"
UTF8_FLAG = 0x800
_NAME_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")


class SkillPackageError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class PackageFile:
    """包内一个资源文件：相对 Skill 根目录的路径与内容哈希。"""

    path: str
    sha256: str
    size: int


@dataclass(frozen=True, slots=True)
class SkillPackage:
    name: str
    description: str
    entry_path: str
    root: str
    body: str
    package_sha256: str
    files: tuple[PackageFile, ...]


def parse_package(data: bytes) -> SkillPackage:
    """校验并解析 ZIP 包：恰好一个 SKILL.md 入口，frontmatter 提供元数据。"""
    if len(data) > MAX_PACKAGE_BYTES:
        raise SkillPackageError(413, "Skill 包不能超过 32MiB")
    try:
        archive = _open_zip(data)
    except (zipfile.BadZipFile, UnicodeDecodeError) as error:
        raise SkillPackageError(422, "不是有效的 ZIP 文件") from error
    with archive:
        infos = archive.infolist()
        entry = _find_entry(infos)
        root = _root_of(entry)
        meta, body = _parse_entry(archive, entry)
        files = _resource_files(archive, infos, entry, root)
        return SkillPackage(
            name=meta[0], description=meta[1], entry_path=entry.filename,
            root=root, body=body, package_sha256=hashlib.sha256(data).hexdigest(),
            files=files,
        )


def open_package(data: bytes) -> zipfile.ZipFile:
    """按上传时相同的规则打开包：保证清单路径与成员名一一对应。"""
    return _open_zip(data)


def _open_zip(data: bytes) -> zipfile.ZipFile:
    archive = zipfile.ZipFile(io.BytesIO(data))
    if any(_needs_utf8(info) for info in archive.infolist()):
        archive.close()
        archive = zipfile.ZipFile(io.BytesIO(data), metadata_encoding="utf-8")
    return archive


def _needs_utf8(info: zipfile.ZipInfo) -> bool:
    """未标记 UTF-8 的成员名若实为 UTF-8 字节，则默认 cp437 解码会乱码。"""
    if info.flag_bits & UTF8_FLAG:
        return False
    try:
        raw = info.filename.encode("cp437")
        decoded = raw.decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return False
    return decoded != info.filename


def _find_entry(infos: list[zipfile.ZipInfo]) -> zipfile.ZipInfo:
    """入口只能是根目录或一级子目录下的 SKILL.md；附属嵌套文件不算 Skill。"""
    candidates = [
        info for info in infos
        if not info.is_dir() and _is_entry_path(info.filename)
    ]
    if not candidates:
        raise SkillPackageError(422, "包内缺少 SKILL.md 入口文件")
    if len(candidates) > 1:
        names = "、".join(info.filename for info in candidates)
        raise SkillPackageError(422, f"包内包含多个 SKILL.md 入口：{names}")
    return candidates[0]


def _is_entry_path(name: str) -> bool:
    path = PurePosixPath(name)
    return path.name == ENTRY_NAME and len(path.parts) <= 2


def _root_of(entry: zipfile.ZipInfo) -> str:
    parts = PurePosixPath(entry.filename).parts
    return parts[0] if len(parts) == 2 else ""


def _parse_entry(
    archive: zipfile.ZipFile, entry: zipfile.ZipInfo
) -> tuple[tuple[str, str], str]:
    text = _decode(archive.read(entry), f"{entry.filename} 不是文本文件")
    try:
        post = frontmatter.loads(text)
    except Exception as error:
        raise SkillPackageError(422, f"SKILL.md frontmatter 解析失败：{error}") from error
    name = _meta_text(post.metadata, "name")
    description = _meta_text(post.metadata, "description")
    _validate_name(name)
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise SkillPackageError(422, "description 不能超过 1024 字符")
    return (name, description), post.content


def _meta_text(metadata: dict, key: str) -> str:
    """frontmatter 字段必须是真实非空字符串：数字/布尔/列表/对象一律拒绝，不做类型强转。"""
    value = metadata.get(key)
    if value is None:
        raise SkillPackageError(422, f"SKILL.md frontmatter 缺少非空 {key}")
    if not isinstance(value, str):
        raise SkillPackageError(
            422, f"SKILL.md frontmatter {key} 必须是字符串，收到{_type_of(value)}"
        )
    text = value.strip()
    if not text:
        raise SkillPackageError(422, f"SKILL.md frontmatter 缺少非空 {key}")
    return text


def _type_of(value: object) -> str:
    if isinstance(value, bool):
        return "布尔值"
    if isinstance(value, (int, float)):
        return "数字"
    if isinstance(value, list):
        return "列表"
    if isinstance(value, dict):
        return "对象"
    return type(value).__name__


def _validate_name(name: str) -> None:
    if not 1 <= len(name) <= MAX_NAME_LENGTH:
        raise SkillPackageError(422, "SKILL.md frontmatter name 长度须为 1-64 字符")
    if not set(name) <= _NAME_CHARACTERS:
        raise SkillPackageError(
            422, "name 只能包含小写字母、数字和连字符（如 sizheng-case-generator）"
        )


def _resource_files(
    archive: zipfile.ZipFile, infos: list[zipfile.ZipInfo], entry: zipfile.ZipInfo, root: str,
) -> tuple[PackageFile, ...]:
    files: list[PackageFile] = []
    seen: set[str] = set()
    total = 0
    for info in infos:
        if info.is_dir() or info is entry:
            continue
        relative = _relative_of(info, root)
        if relative is None:
            continue
        _require_safe_new(relative, seen)
        total += info.file_size
        files.append(_package_file(archive, info, relative))
    _require_size_limits(len(files), total)
    return tuple(files)


def _require_safe_new(relative: str, seen: set[str]) -> None:
    """路径必须安全且首次出现；ZIP 允许同名成员，重复会破坏清单与读取一致性。"""
    _require_safe(relative)
    if relative in seen:
        raise SkillPackageError(422, f"包内存在重复资源路径：{relative}")
    seen.add(relative)


def _package_file(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, relative: str
) -> PackageFile:
    return PackageFile(
        path=relative, sha256=_file_hash(archive, info), size=info.file_size,
    )


def _require_size_limits(count: int, total: int) -> None:
    if count > MAX_PACKAGE_FILES:
        raise SkillPackageError(422, "包内文件数量不能超过 1000")
    if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
        raise SkillPackageError(422, "包内文件解压后总大小不能超过 64MiB")


def _relative_of(info: zipfile.ZipInfo, root: str) -> str | None:
    """只保留 Skill 根目录内的文件，返回相对路径；入口自身在调用处排除。"""
    name = info.filename
    if not root:
        return name
    prefix = f"{root}/"
    return name[len(prefix):] if name.startswith(prefix) else None


def _require_safe(relative: str) -> None:
    path = PurePosixPath(relative)
    if (
        not relative or relative != str(path)
        or path.is_absolute() or ".." in path.parts or "\\" in relative
        or any(part.startswith(".") for part in path.parts)
    ):
        raise SkillPackageError(422, f"包内存在不安全的资源路径：{relative!r}")


def _file_hash(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(info) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode(data: bytes, error_detail: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SkillPackageError(422, error_detail) from error
