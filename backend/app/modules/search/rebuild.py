from __future__ import annotations

from app.core.bootstrap import bootstrap
from app.core.config import Settings
from app.core.database import connect
from app.modules.search.client import create_client
from app.modules.search.indexer import CatalogRebuilder


def main() -> int:
    settings = Settings.from_environment()
    mongo, database = connect(settings)
    client = create_client(settings.search_url, settings.search_api_key_file)
    try:
        bootstrap(database, settings)
        count = CatalogRebuilder(database, client, settings.search_index_uid).rebuild()
        print(f"检索目录已重建：{count} 条")
        return 0
    finally:
        mongo.close()


if __name__ == "__main__":
    raise SystemExit(main())
