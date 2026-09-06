"""Skill 平台 HTTP：管理员上传/查看/发布；教师目录与按需内容、资源读取。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile
from fastapi.param_functions import File
from pydantic import BaseModel, ConfigDict

from app.core.dependencies import get_blob_store, get_database
from app.modules.auth.dependencies import require_csrf, require_user
from app.modules.attachments.storage import BlobStore
from app.modules.skills.parse import MAX_PACKAGE_BYTES
from app.modules.skills.service import (
    SkillError,
    admin_list,
    publish_version,
    read_published_content,
    read_published_resource,
    published_catalog,
    upload_package,
)

admin_router = APIRouter(prefix="/api/admin/skills", tags=["skills"])
router = APIRouter(prefix="/api/skills", tags=["skills"])


class PublishBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    versionId: str


def _require_admin(user: dict) -> None:
    if user["role"] != "admin":
        raise SkillError(403, "仅管理员可执行此操作")


def _package_bytes(upload: UploadFile) -> bytes:
    data = upload.file.read(MAX_PACKAGE_BYTES + 1)
    if len(data) > MAX_PACKAGE_BYTES:
        raise SkillError(413, "Skill 包不能超过 32MiB")
    if not data:
        raise SkillError(422, "Skill 包内容为空")
    return data


@admin_router.post("/packages", status_code=201)
def upload_skill_package(
    file: UploadFile = File(...),
    database=Depends(get_database),
    store: BlobStore = Depends(get_blob_store),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
) -> dict:
    _require_admin(user)
    return upload_package(database, store, _package_bytes(file))


@admin_router.get("")
def list_skills(
    database=Depends(get_database),
    user: dict = Depends(require_user),
) -> list:
    _require_admin(user)
    return admin_list(database)


@admin_router.post("/{skill_id}/publish")
def publish_skill(
    skill_id: str,
    body: PublishBody,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
) -> dict:
    _require_admin(user)
    return {"skill": publish_version(database, skill_id, body.versionId)}


@router.get("")
def skill_catalog(
    database=Depends(get_database),
    user: dict = Depends(require_user),
) -> list:
    return published_catalog(database)


@router.get("/{skill_id}/content")
def skill_content(
    skill_id: str,
    database=Depends(get_database),
    store: BlobStore = Depends(get_blob_store),
    user: dict = Depends(require_user),
) -> dict:
    return read_published_content(database, store, skill_id)


@router.get("/{skill_id}/resources/{resource_path:path}")
def skill_resource(
    skill_id: str,
    resource_path: str,
    database=Depends(get_database),
    store: BlobStore = Depends(get_blob_store),
    user: dict = Depends(require_user),
) -> dict:
    return read_published_resource(database, store, skill_id, resource_path)
