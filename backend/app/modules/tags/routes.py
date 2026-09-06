from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import get_database
from app.modules.auth.dependencies import require_csrf, require_user
from app.modules.tags.models import TagCreate, TagGroupCreate, TagGroupPatch, TagPatch
from app.modules.tags.service import (
    create_group,
    create_tag,
    list_groups,
    update_group,
    update_tag,
)

DatabaseDependency = Annotated[object, Depends(get_database)]
UserDependency = Annotated[dict, Depends(require_user)]

group_router = APIRouter(prefix="/api/tag-groups", tags=["tags"])
tag_router = APIRouter(prefix="/api/tags", tags=["tags"])


@group_router.get("")
def index(database: DatabaseDependency):
    return list_groups(database)


@group_router.post("", status_code=201)
def create(
    body: TagGroupCreate,
    database: DatabaseDependency,
    user: UserDependency,
    _csrf: dict = Depends(require_csrf),
):
    return create_group(database, body.model_dump(by_alias=True), user)


@group_router.patch("/{group_id}")
def save(
    group_id: str,
    body: TagGroupPatch,
    database: DatabaseDependency,
    user: UserDependency,
    _csrf: dict = Depends(require_csrf),
):
    return update_group(database, group_id, body.model_dump(by_alias=True), user)


@group_router.post("/{group_id}/tags", status_code=201)
def add_tag(
    group_id: str,
    body: TagCreate,
    database: DatabaseDependency,
    user: UserDependency,
    _csrf: dict = Depends(require_csrf),
):
    return create_tag(database, group_id, body.model_dump(by_alias=True), user)


@tag_router.patch("/{tag_id}")
def save_tag(
    tag_id: str,
    body: TagPatch,
    database: DatabaseDependency,
    user: UserDependency,
    _csrf: dict = Depends(require_csrf),
):
    return update_tag(database, tag_id, body.model_dump(by_alias=True), user)
