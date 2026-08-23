from __future__ import annotations

import json
from pathlib import Path

from pymongo.database import Database

SEED_PATH = Path(__file__).resolve().parents[4] / "files" / "cases_seed.json"


def _seed_case(database: Database, seed: dict) -> None:
    case = seed["case"]
    database.cases.update_one({"id": case["id"]}, {"$setOnInsert": case}, upsert=True)
    version = seed.get("version")
    if version:
        database.case_versions.update_one(
            {"id": version["id"]}, {"$setOnInsert": version}, upsert=True
        )


def seed_demo_cases(database: Database) -> None:
    seeds = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    for seed in seeds:
        _seed_case(database, seed)
