from __future__ import annotations

from app.core.bootstrap import bootstrap
from app.core.config import Settings
from app.core.database import connect


def main() -> int:
    settings = Settings.from_environment()
    client, database = connect(settings)
    try:
        bootstrap(database, settings)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
