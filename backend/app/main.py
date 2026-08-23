from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.database import Database

from app.api.router import router
from app.core.bootstrap import bootstrap
from app.core.config import Settings
from app.core.database import connect
from app.modules.attachments.service import AttachmentError
from app.modules.attachments.storage import BlobStore, minio_blob_store
from app.modules.cases.service import CaseError, RevisionConflict
from app.modules.materials.errors import MaterialImportError
from app.modules.search.client import create_reader
from app.modules.search.meilisearch import MeilisearchCatalog, SearchUnavailable
from app.modules.search.state import MongoCatalogState


def _case_error(_request: Request, error: CaseError) -> JSONResponse:
    content = {"detail": error.detail}
    if isinstance(error, RevisionConflict):
        content["currentRevision"] = error.current_revision
    return JSONResponse(status_code=error.status_code, content=content)


def _attachment_error(_request: Request, error: AttachmentError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail})


def _material_error(_request: Request, error: MaterialImportError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail})


def _search_error(_request: Request, error: SearchUnavailable) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(error)})


def _build_app(database, settings, lifespan, catalog, catalog_state) -> FastAPI:
    api = FastAPI(title="Case Library API", lifespan=lifespan)
    api.state.database = database
    api.state.settings = settings
    api.state.search_catalog = catalog
    api.state.catalog_state = catalog_state
    api.add_exception_handler(CaseError, _case_error)
    api.add_exception_handler(AttachmentError, _attachment_error)
    api.add_exception_handler(MaterialImportError, _material_error)
    api.add_exception_handler(SearchUnavailable, _search_error)
    api.include_router(router)
    return api


def _catalog(settings: Settings):
    reader = create_reader(settings.search_url, settings.search_api_key_file)
    return MeilisearchCatalog(reader)


def _lifespan(database, settings, mongo_client, blob_store, catalog):
    @asynccontextmanager
    async def lifespan(api: FastAPI):
        try:
            api.state.blob_store = blob_store or minio_blob_store(settings)
            api.state.search_catalog = catalog or _catalog(settings)
            bootstrap(database, settings)
            yield
        finally:
            if mongo_client is not None:
                mongo_client.close()

    return lifespan


def create_app(
    database: Database | None = None,
    settings: Settings | None = None,
    blob_store: BlobStore | None = None,
    search_catalog=None,
    catalog_state=None,
) -> FastAPI:
    active_settings = settings or Settings.from_environment()
    client, active_database = (
        (None, database) if database is not None else connect(active_settings)
    )
    lifespan = _lifespan(
        active_database,
        active_settings,
        client,
        blob_store,
        search_catalog,
    )
    state = catalog_state or MongoCatalogState(active_database)
    return _build_app(active_database, active_settings, lifespan, search_catalog, state)


app = create_app()
