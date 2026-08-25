from __future__ import annotations

import json
from pathlib import Path

from pymongo.database import Database

SEED_PATH = Path(__file__).resolve().parents[4] / "files" / "materials_seed.json"
ACCESS_LEVELS = {0: "public", 1: "campus", 2: "private"}
KNOWN_TYPES = ("政策文件", "统计数据", "视频影像", "图片", "学术论文")
MATERIAL_FIELDS = (
    "id",
    "title",
    "summary",
    "excerpt",
    "source",
    "sourceUrl",
    "tags",
    "publishedAt",
    "collectedAt",
    "citedCount",
    "createdAt",
    "updatedAt",
)


def _material_type(row: dict) -> str:
    return next((tag for tag in row.get("tags", []) if tag in KNOWN_TYPES), row["kind"])


def _authority(row: dict) -> str:
    if row.get("grade") in {"S", "A"}:
        return "original"
    return "secondary" if row.get("grade") == "B" else "pending"


def _material(row: dict) -> dict:
    return {
        **{field: row.get(field) for field in MATERIAL_FIELDS},
        "materialType": _material_type(row),
        "authority": _authority(row),
        "accessLevel": ACCESS_LEVELS[row["level"]],
        "status": "active" if row["status"] == "正常" else "disabled",
        "createdBy": "u-admin-demo",
        "publicReferenceCount": 0,
    }


def seed_demo_materials(database: Database) -> None:
    rows = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    for row in rows:
        material = _material(row)
        database.materials.update_one(
            {"id": material["id"]}, {"$setOnInsert": material}, upsert=True
        )
