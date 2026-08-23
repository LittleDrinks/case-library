from __future__ import annotations

from io import StringIO

import mongomock
import pytest

from app.cli.bootstrap_admin import AdminBootstrapError, bootstrap_admin, main
from app.core.database import initialize
from app.modules.auth.passwords import verify_password

STRONG_PASSWORD = "Production-Admin-2026!"


@pytest.fixture
def database():
    database = mongomock.MongoClient()["bootstrap_admin"]
    database.client.admin.command = lambda _name: {"ok": 1}
    initialize(database)
    return database


def test_bootstrap_admin_reads_password_from_stdin(database) -> None:
    output = StringIO()
    status = main(
        ["--username", "principal", "--name", "首任管理员"],
        input_stream=StringIO(f"{STRONG_PASSWORD}\n"),
        output_stream=output,
        database=database,
    )
    user = database.users.find_one({"username": "principal"})

    assert status == 0
    assert user["role"] == "admin"
    assert user["status"] == "active"
    assert user["must_change_password"] is False
    assert verify_password(STRONG_PASSWORD, user["password_hash"])
    assert STRONG_PASSWORD not in output.getvalue()


def test_bootstrap_admin_is_create_only(database) -> None:
    bootstrap_admin(database, "principal", "首任管理员", STRONG_PASSWORD)

    with pytest.raises(AdminBootstrapError, match="已存在"):
        bootstrap_admin(database, "principal", "另一个人", "Another-Strong-2026!")

    assert database.users.count_documents({"username": "principal"}) == 1


def test_bootstrap_admin_rejects_weak_password(database) -> None:
    with pytest.raises(AdminBootstrapError, match="至少 12"):
        bootstrap_admin(database, "principal", "首任管理员", "too-short")

    assert database.users.count_documents({}) == 0


def test_connected_cli_rejects_non_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "demo")
    monkeypatch.setenv("ENABLE_DEMO_SEED", "false")

    with pytest.raises(AdminBootstrapError, match="仅允许在 production"):
        main(
            ["--username", "principal", "--name", "首任管理员"],
            input_stream=StringIO(f"{STRONG_PASSWORD}\n"),
        )
