"""Canonical API router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.routes import ai, auth, cases, public, reviews

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(ai.router)
api_router.include_router(cases.router)
api_router.include_router(reviews.router)
api_router.include_router(public.router)

__all__ = ["api_router"]
