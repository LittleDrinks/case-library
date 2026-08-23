from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

AccessLevel = Literal["public", "campus", "private"]


class AttachmentView(BaseModel):
    id: str
    name: str
    mediaType: str
    size: int
    accessLevel: AccessLevel
    createdAt: str
