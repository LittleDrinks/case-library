from __future__ import annotations

from fastapi import Request

from app.core.config import Settings


def get_database(request: Request):
    return request.app.state.database


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_blob_store(request: Request):
    return request.app.state.blob_store


def get_search_catalog(request: Request):
    return request.app.state.search_catalog


def get_catalog_state(request: Request):
    return request.app.state.catalog_state
