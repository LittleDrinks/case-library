from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from pymongo.database import Database

from app.core.config import Settings
from app.core.database import connect, initialize
from app.modules.auth.admin_bootstrap import AdminBootstrapError, bootstrap_admin

__all__ = ["AdminBootstrapError", "bootstrap_admin", "main"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create the first production administrator"
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--name", required=True)
    return parser


def _read_password(stream: TextIO) -> str:
    return stream.readline().rstrip("\r\n")


def _create(database: Database, args: argparse.Namespace, password: str) -> dict:
    initialize(database)
    return bootstrap_admin(database, args.username, args.name, password)


def _production_settings() -> Settings:
    settings = Settings.from_environment()
    if settings.app_environment.strip().lower() != "production":
        raise AdminBootstrapError("管理员 bootstrap 仅允许在 production 环境运行")
    return settings


def _create_connected(args: argparse.Namespace, password: str) -> dict:
    client, database = connect(_production_settings())
    try:
        return _create(database, args, password)
    finally:
        client.close()


def main(
    argv: Sequence[str] | None = None,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    database: Database | None = None,
) -> int:
    args = _parser().parse_args(argv)
    password = _read_password(input_stream or sys.stdin)
    user = (
        _create(database, args, password)
        if database is not None
        else _create_connected(args, password)
    )
    print(f"已创建生产管理员：{user['username']}", file=output_stream or sys.stdout)
    return 0


def _entrypoint() -> int:
    try:
        return main()
    except AdminBootstrapError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
