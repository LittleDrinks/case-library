from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from minio.error import MinioException
from pymongo.errors import PyMongoError
from urllib3.exceptions import HTTPError

from app.core.dependencies import (
    get_blob_store,
    get_catalog_state,
    get_database,
    get_search_catalog,
)
from app.modules.search.meilisearch import SearchUnavailable

router = APIRouter()


@router.get("/health/live")
def live() -> dict:
    return {"status": "ok"}


def _mongo_ready(database) -> None:
    try:
        hello = database.client.admin.command("hello")
    except PyMongoError as error:
        raise HTTPException(status_code=503, detail="MongoDB unavailable") from error
    if not hello.get("isWritablePrimary"):
        raise HTTPException(status_code=503, detail="MongoDB is not writable")


def _object_store_ready(blob_store) -> None:
    try:
        blob_store.health()
    except (HTTPError, MinioException, OSError) as error:
        raise HTTPException(
            status_code=503, detail="Object storage unavailable"
        ) from error


def _search_ready(catalog_state, catalog) -> None:
    try:
        target = catalog_state.read().target
        catalog.health(target.index_uid, target.generation, target.index_epoch)
    except (SearchUnavailable, PyMongoError) as error:
        raise HTTPException(
            status_code=503, detail="Search catalog unavailable"
        ) from error


@router.get("/health/ready")
def ready(
    database=Depends(get_database),
    blob_store=Depends(get_blob_store),
    catalog=Depends(get_search_catalog),
    catalog_state=Depends(get_catalog_state),
) -> dict:
    _mongo_ready(database)
    _object_store_ready(blob_store)
    _search_ready(catalog_state, catalog)
    return {"status": "ready"}


@router.get("/api/constants")
def constants() -> dict:
    return {
        "caseWorkflowStatuses": ["draft", "pending", "reviewing", "published"],
        "casePublicationStatuses": ["none", "public", "hidden"],
        "roles": ["user", "admin"],
        "csrfHeader": "X-CSRF-Token",
    }
