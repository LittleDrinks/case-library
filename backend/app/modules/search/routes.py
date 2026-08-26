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
from app.modules.search.service import CatalogSearch, search_catalog

router = APIRouter(prefix="/api/search", tags=["search"])
DatabaseDependency = Annotated[object, Depends(get_database)]
CatalogDependency = Annotated[object, Depends(get_search_catalog)]
CatalogStateDependency = Annotated[object, Depends(get_catalog_state)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
UserDependency = Annotated[dict | None, Depends(optional_user)]


@router.get("")
def search(
    query: Annotated[SearchQuery, Query()],
    database: DatabaseDependency,
    catalog: CatalogDependency,
    catalog_state: CatalogStateDependency,
    settings: SettingsDependency,
    user: UserDependency,
):
    catalog_search = CatalogSearch(query, user, settings.app_secret_file)
    return search_catalog(
        database,
        catalog,
        catalog_state,
        catalog_search,
    )
