from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.config import Settings
from app.core.dependencies import (
    get_catalog_state,
    get_database,
    get_search_catalog,
    get_settings,
)
from app.modules.auth.dependencies import optional_user
from app.modules.search.models import SearchQuery
from app.modules.search.service import search_catalog

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(query: Annotated[SearchQuery, Query()], database=Depends(get_database), catalog=Depends(get_search_catalog), catalog_state=Depends(get_catalog_state), settings: Settings = Depends(get_settings), user: dict | None = Depends(optional_user)):
    return search_catalog(
        database,
        catalog,
        catalog_state,
        user,
        query.q,
        query.kind,
        query.cursor,
        query.page_size,
        query.filters(),
        settings.app_secret_file,
    )
