from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import get_database
from app.modules.knowledge.service import knowledge_detail

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/{knowledge_id}")
def show(knowledge_id: str, database=Depends(get_database)):
    return knowledge_detail(database, knowledge_id)
