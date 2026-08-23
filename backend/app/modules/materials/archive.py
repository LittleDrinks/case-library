from __future__ import annotations

import mimetypes
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

import libarchive
from fastapi import UploadFile
from libarchive.exception import ArchiveError

from app.modules.materials.errors import MaterialImportError

MAX_REQUEST_BYTES = 128 * 1024 * 1024
MAX_ITEM_BYTES = 128 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_ITEMS = 500
MAX_COMPRESSION_RATIO = 100
ARCHIVE_SUFFIXES = {".zip", ".rar"}
ZIP_CONTAINER_SUFFIXES = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}
EXECUTABLE_SUFFIXES = {".bat", ".cmd", ".com", ".exe", ".msi", ".ps1", ".sh"}
KNOWN_SIGNATURES = {
    ".gif": (b"GIF87a", b"GIF89a"),
    ".jpeg": (b"\xff\xd8\xff",),
    ".jpg": (b"\xff\xd8\xff",),
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
}


@dataclass(frozen=True, slots=True)
class PreparedFile:
    filename: str
    media_type: str
    size: int
    path: Path | None
    error: str | None = None


@dataclass(slots=True)
class RequestBudget:
    expanded: int = 0
    count: int = 0


@dataclass(slots=True)
class ArchiveBudget:
    source_size: int
    request: RequestBudget
    expanded: int = 0
    count: int = 0


def _filename(value: str) -> str:
    return PurePosixPath(value.replace("\\", "/")).name or "unnamed"


def _media_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _path_error(value: str) -> str | None:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if len(normalized) > 255:
        return "文件路径不能超过 255 个字符"
    if path.is_absolute() or ".." in path.parts:
        return "文件路径不安全"
    if path.parts and path.parts[0].endswith(":"):
        return "文件路径不安全"
    return None


def _signature(path: Path) -> bytes:
    with path.open("rb") as source:
        return source.read(8)


def _is_archive(path: Path, filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    if suffix in ARCHIVE_SUFFIXES:
        return True
    if suffix in ZIP_CONTAINER_SUFFIXES:
        return False
    magic = _signature(path)
    return magic.startswith(b"PK") or magic.startswith(b"Rar!\x1a\x07")


def _is_executable(filename: str, mode: int, magic: bytes = b"") -> bool:
    suffix = Path(filename).suffix.lower()
    signatures = (b"MZ", b"\x7fELF", b"#!", b"\xfe\xed\xfa", b"\xcf\xfa\xed")
    return (
        suffix in EXECUTABLE_SUFFIXES
        or bool(mode & 0o111)
        or magic.startswith(signatures)
    )


def _signature_error(filename: str, magic: bytes) -> str | None:
    suffix = Path(filename).suffix.lower()
    expected = (
        (b"PK",) if suffix in ZIP_CONTAINER_SUFFIXES else KNOWN_SIGNATURES.get(suffix)
    )
    if expected and not magic.startswith(expected):
        return "文件扩展名与内容不匹配"
    return None


def _copy_source(upload: UploadFile, destination: Path) -> int:
    size = 0
    upload.file.seek(0)
    with destination.open("wb") as target:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_REQUEST_BYTES:
                raise MaterialImportError(413, "导入请求不能超过 128MiB")
            target.write(chunk)
    return size


def _direct(upload: UploadFile, path: Path, size: int) -> PreparedFile:
    name = upload.filename or "unnamed"
    error = _path_error(name)
    if not error:
        error = _payload_error(path, name)
    return PreparedFile(
        name, upload.content_type or _media_type(name), size, path, error
    )


def _direct_file(
    upload: UploadFile, path: Path, size: int, budget: RequestBudget
) -> PreparedFile:
    budget.count += 1
    budget.expanded += size
    _require_archive_limits(0, budget.expanded, budget.count)
    return _direct(upload, path, size)


def _entry_error(entry) -> str | None:
    if error := _path_error(entry.pathname or ""):
        return error
    if entry.issym or entry.islnk or entry.isdev or not entry.isfile:
        return "不允许导入链接或设备文件"
    if Path(entry.pathname).suffix.lower() in ARCHIVE_SUFFIXES:
        return "不允许嵌套归档"
    if _is_executable(entry.pathname, entry.perm):
        return "不允许导入可执行文件"
    return None


def _write_entry(entry, destination: Path, budget: ArchiveBudget) -> int:
    size = 0
    _require_item_size(max(entry.size or 0, 0))
    _require_budgets(budget, max(entry.size or 0, 0))
    with destination.open("wb") as target:
        for block in entry.get_blocks():
            size += len(block)
            _require_item_size(size)
            _require_budgets(budget, size)
            target.write(block)
    _record_expanded(budget, size)
    return size


def _require_item_size(size: int) -> None:
    if size > MAX_ITEM_BYTES:
        raise MaterialImportError(413, "归档内单个文件不能超过 128MiB")


def _payload_error(path: Path, filename: str) -> str | None:
    magic = _signature(path)
    suffix = Path(filename).suffix.lower()
    nested_zip = magic.startswith(b"PK") and suffix not in ZIP_CONTAINER_SUFFIXES
    if nested_zip or magic.startswith(b"Rar!\x1a\x07"):
        return "不允许嵌套归档"
    if _is_executable(filename, 0, magic):
        return "不允许导入可执行文件"
    return _signature_error(filename, magic)


def _failed_entry(entry, filename: str, budget: ArchiveBudget) -> PreparedFile:
    _record_expanded(budget, max(entry.size or 0, 0))
    return PreparedFile(
        filename, _media_type(filename), entry.size or 0, None, _entry_error(entry)
    )


def _require_budgets(budget: ArchiveBudget, pending: int = 0) -> None:
    _require_archive_limits(budget.source_size, budget.expanded + pending, budget.count)
    _require_archive_limits(0, budget.request.expanded + pending, budget.request.count)


def _record_expanded(budget: ArchiveBudget, size: int) -> None:
    _require_budgets(budget, size)
    budget.expanded += size
    budget.request.expanded += size


def _count_entry(budget: ArchiveBudget) -> None:
    budget.count += 1
    budget.request.count += 1
    _require_budgets(budget)


def _prepare_entry(
    entry, directory: Path, order: int, budget: ArchiveBudget
) -> PreparedFile | None:
    _count_entry(budget)
    if entry.isdir:
        if _path_error(entry.pathname or ""):
            raise MaterialImportError(400, "归档目录路径不安全")
        return None
    _require_item_size(max(entry.size or 0, 0))
    filename = _filename(entry.pathname or "unnamed")
    error = _entry_error(entry)
    if error:
        return _failed_entry(entry, filename, budget)
    destination = directory / f"entry-{order}"
    size = _write_entry(entry, destination, budget)
    error = _payload_error(destination, filename)
    return PreparedFile(filename, _media_type(filename), size, destination, error)


def _require_archive_limits(size: int, expanded: int, count: int) -> None:
    if count > MAX_ITEMS:
        raise MaterialImportError(413, "单次导入最多 500 项")
    if expanded > MAX_EXPANDED_BYTES:
        raise MaterialImportError(413, "归档展开后不能超过 1GiB")
    if size and expanded > size * MAX_COMPRESSION_RATIO:
        raise MaterialImportError(413, "归档压缩比不能超过 100")


def _expand(path: Path, directory: Path, request: RequestBudget) -> list[PreparedFile]:
    prepared = []
    budget = ArchiveBudget(path.stat().st_size, request)
    with libarchive.file_reader(str(path)) as archive:
        for order, entry in enumerate(archive):
            item = _prepare_entry(entry, directory, order, budget)
            if not item:
                continue
            prepared.append(item)
    return prepared


def _archive_files(
    path: Path, directory: Path, filename: str, budget: RequestBudget
) -> list[PreparedFile]:
    count_before = budget.count
    try:
        prepared = _expand(path, directory, budget)
    except ArchiveError:
        prepared = []
    if prepared:
        return prepared
    _count_unreadable_archive(budget, count_before)
    return [_unreadable_archive(path, filename)]


def _count_unreadable_archive(budget: RequestBudget, previous: int) -> None:
    if budget.count != previous:
        return
    budget.count += 1
    _require_archive_limits(0, budget.expanded, budget.count)


def _unreadable_archive(path: Path, filename: str) -> PreparedFile:
    return PreparedFile(
        filename,
        _media_type(filename),
        path.stat().st_size,
        None,
        "无法读取归档文件",
    )


def _prepare_upload(
    upload: UploadFile,
    source: Path,
    directory: Path,
    order: int,
    budget: RequestBudget,
) -> list[PreparedFile]:
    if not _is_archive(source, upload.filename or ""):
        return [_direct_file(upload, source, source.stat().st_size, budget)]
    archive_directory = directory / f"archive-{order}"
    archive_directory.mkdir()
    return _archive_files(
        source, archive_directory, upload.filename or "unnamed", budget
    )


def _require_request_size(size: int) -> None:
    if size > MAX_REQUEST_BYTES:
        raise MaterialImportError(413, "导入请求不能超过 128MiB")


@contextmanager
def prepare_files(uploads: list[UploadFile]):
    with TemporaryDirectory(prefix="material-import-") as temporary:
        directory, prepared, actual_size = Path(temporary), [], 0
        budget = RequestBudget()
        for order, upload in enumerate(uploads):
            source = directory / f"source-{order}"
            actual_size += _copy_source(upload, source)
            _require_request_size(actual_size)
            prepared.extend(_prepare_upload(upload, source, directory, order, budget))
        yield prepared
