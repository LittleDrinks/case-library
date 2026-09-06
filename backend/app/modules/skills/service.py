"""Skill 平台服务：上传（不可变版本）、发布、目录、按需内容与资源读取。

版本号由 Skill 文档原子自增分配，并发上传各得唯一版本；发布仅移动指针，
版本内容与包字节一旦写入不再变更；资源按版本清单读取。
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.database import Database

from app.core.ids import new_id
from app.modules.attachments.storage import BlobStore
from app.modules.skills.parse import (
    PackageFile,
    SkillPackage,
    SkillPackageError,
    open_package,
    parse_package,
)


class SkillError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class BoundSkill:
    """已发布 Skill 版本的只读快照：内容与清单在版本生命周期内不变。"""

    skill_id: str
    version_id: str
    version: str
    package_sha256: str
    store: BlobStore
    body: str
    description: str
    entry_path: str
    root: str
    files: tuple[PackageFile, ...]

    def read_resource(self, path: str) -> str:
        for file in self.files:
            if file.path == path:
                return self._read(file)
        raise SkillError(404, f"资源不存在：{path}")

    def _read(self, file: PackageFile) -> str:
        archive = _load_zip(self.store, self.package_sha256)
        with archive:
            info = _member(archive, _archive_path(self.root, file.path))
            data = archive.read(info)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SkillError(422, f"资源不是文本文件：{file.path}") from error


def upload_package(database: Database, store: BlobStore, data: bytes) -> dict:
    """解析并保存新版本：同一 Skill 再次上传产生 v2、v3…，历史版本不可变。"""
    package = parse_package(data)
    now = _now()
    store.put(package.package_sha256, io.BytesIO(data), len(data), "application/zip")
    number = _reserve_version_number(database, package.name, now)
    version = _insert_version(database, package, number, now)
    skill = _mark_latest_version(database, package, version["id"], now)
    return {"skill": skill_view(skill), "version": version_view(version)}


def publish_version(database: Database, skill_id: str, version_id: str) -> dict:
    """发布指定版本：仅移动已发布指针；重复发布同一版本幂等。"""
    version = _skill_version(database, skill_id, version_id)
    now = _now()
    skill = database.skills.find_one_and_update(
        {"id": skill_id},
        {"$set": {"publishedVersionId": version["id"], "publishedAt": now}},
        return_document=ReturnDocument.AFTER,
    )
    if skill is None:
        raise SkillError(404, "Skill 不存在")
    return skill_view(skill)


def admin_list(database: Database) -> list[dict]:
    skills = []
    for skill in database.skills.find().sort("createdAt", 1):
        versions = database.skill_versions.find(
            {"skillId": skill["id"]}
        ).sort("createdAt", 1)
        skills.append({**skill_view(skill), "versions": [version_view(v) for v in versions]})
    return skills


def published_catalog(database: Database) -> list[dict]:
    skills = []
    for skill in database.skills.find({"publishedVersionId": {"$type": "string"}}):
        version = database.skill_versions.find_one({"id": skill["publishedVersionId"]})
        if version:
            skills.append(catalog_view(skill, version))
    return skills


def get_published_version(database: Database, skill_id: str) -> dict | None:
    skill = database.skills.find_one({"id": skill_id})
    if not skill or not skill.get("publishedVersionId"):
        return None
    return database.skill_versions.find_one({"id": skill["publishedVersionId"]})


def read_published_content(database: Database, store: BlobStore, skill_id: str) -> dict:
    """服务端读取已发布版本 SKILL.md 正文（不含 frontmatter）。"""
    version = _published_bound(database, store, skill_id)
    return {
        "skillId": skill_id, "versionId": version.version_id,
        "version": version.version, "packageSha256": version.package_sha256,
        "path": version.entry_path, "name": version.skill_id,
        "description": version.description, "content": version.body,
    }


def read_published_resource(
    database: Database, store: BlobStore, skill_id: str, path: str
) -> dict:
    bound = _published_bound(database, store, skill_id)
    content = bound.read_resource(path)
    file = next(item for item in bound.files if item.path == path)
    return {
        "skillId": skill_id, "versionId": bound.version_id, "version": bound.version,
        "path": path, "sha256": file.sha256, "size": file.size, "content": content,
    }


def _published_bound(database: Database, store: BlobStore, skill_id: str) -> BoundSkill:
    version = get_published_version(database, skill_id)
    if version is None:
        raise SkillError(404, "Skill 不存在或未发布")
    entry = version["entryPath"]
    return BoundSkill(
        skill_id=skill_id, version_id=version["id"], version=version["version"],
        package_sha256=version["packageSha256"], store=store, body=version["body"],
        description=version["description"], entry_path=entry, root=_root_of(entry),
        files=tuple(PackageFile(**file) for file in version["files"]),
    )


def _root_of(entry_path: str) -> str:
    return entry_path.rsplit("/", 1)[0] if "/" in entry_path else ""


def _archive_path(root: str, relative: str) -> str:
    return f"{root}/{relative}" if root else relative


def _insert_version(
    database: Database, package: SkillPackage, number: int, now: str
) -> dict:
    version = {
        "id": new_id("skillver"), "skillId": package.name,
        "version": f"v{number}", "packageSha256": package.package_sha256,
        "entryPath": package.entry_path, "name": package.name,
        "description": package.description, "body": package.body,
        "size": sum(file.size for file in package.files),
        "fileCount": len(package.files),
        "files": [
            {"path": file.path, "sha256": file.sha256, "size": file.size}
            for file in package.files
        ],
        "createdAt": now,
    }
    database.skill_versions.insert_one(version)
    return version


def _reserve_version_number(database: Database, skill_id: str, now: str) -> int:
    """Skill 文档原子自增分配版本号：并发上传各得唯一号码，唯一索引仅兜底。"""
    skill = database.skills.find_one_and_update(
        {"id": skill_id},
        {
            "$inc": {"versionCounter": 1},
            "$setOnInsert": {"id": skill_id, "createdAt": now},
        },
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    return int(skill["versionCounter"])


def _mark_latest_version(
    database: Database, package: SkillPackage, version_id: str, now: str
) -> dict:
    """版本落库后再指向最新：latestVersionId 只指向真实存在的版本。"""
    skill = database.skills.find_one_and_update(
        {"id": package.name},
        {
            "$set": {
                "latestVersionId": version_id, "name": package.name,
                "description": package.description, "updatedAt": now,
            },
        },
        return_document=ReturnDocument.AFTER,
    )
    return skill


def _skill_version(database: Database, skill_id: str, version_id: str) -> dict:
    version = database.skill_versions.find_one({"id": version_id, "skillId": skill_id})
    if version is None:
        raise SkillError(404, "Skill 版本不存在")
    return version


def _load_zip(store: BlobStore, package_sha256: str) -> zipfile.ZipFile:
    data = b"".join(store.open(package_sha256))
    try:
        return open_package(data)
    except (SkillPackageError, zipfile.BadZipFile) as error:
        raise SkillError(422, "Skill 包内容损坏") from error


def _member(archive: zipfile.ZipFile, path: str):
    infos = {info.filename: info for info in archive.infolist() if not info.is_dir()}
    if path not in infos:
        raise SkillError(404, f"资源不存在：{path}")
    return infos[path]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def skill_view(skill: dict) -> dict:
    return {
        "id": skill["id"], "name": skill.get("name"),
        "description": skill.get("description"), "createdAt": skill["createdAt"],
        "latestVersionId": skill.get("latestVersionId"),
        "publishedVersionId": skill.get("publishedVersionId"),
        "publishedAt": skill.get("publishedAt"),
    }


def version_view(version: dict) -> dict:
    return {
        "id": version["id"], "skillId": version["skillId"],
        "version": version["version"], "packageSha256": version["packageSha256"],
        "size": version["size"], "fileCount": version["fileCount"],
        "name": version["name"], "description": version["description"],
        "createdAt": version["createdAt"],
    }


def catalog_view(skill: dict, version: dict) -> dict:
    return {
        "id": skill["id"], "versionId": version["id"], "version": version["version"],
        "name": version["name"], "description": version["description"],
    }
