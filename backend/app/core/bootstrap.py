from __future__ import annotations

from pymongo.database import Database

from app.core.config import Settings
from app.core.database import initialize
from app.modules.auth.seed import reject_demo_accounts, seed_demo_users
from app.modules.cases.seed import seed_demo_cases
from app.modules.knowledge.seed import seed_knowledge
from app.modules.materials.seed import seed_demo_materials


def bootstrap(database: Database, settings: Settings) -> None:
    if settings.app_environment.strip().lower() == "production":
        reject_demo_accounts(database)
    initialize(database)
    seed_knowledge(database)
    if settings.enable_demo_seed:
        seed_demo_users(database)
        seed_demo_cases(database)
        seed_demo_materials(database)
