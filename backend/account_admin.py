#!/usr/bin/env python3
"""Back-office account administration commands."""

import argparse
import csv
import os
import sys
from typing import Dict

sys.path.insert(0, os.path.dirname(__file__))

from database import (
    clear_users,
    create_user,
    delete_user,
    get_user_by_username,
    init_db,
    list_users,
    rename_user,
    set_user_password,
    update_user_fields,
)


def parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in ("1", "true", "yes", "y", "是"):
        return True
    if normalized in ("0", "false", "no", "n", "否"):
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def print_users():
    users = list_users()
    if not users:
        print("No accounts found.")
        return
    for user in users:
        print(
            f"{user.get('username')}\t"
            f"{user.get('role')}\t"
            f"{user.get('nickname', '')}\t"
            f"must_change_password={user.get('must_change_password')}\t"
            f"status={user.get('status')}"
        )


def create_account(args):
    user_id = create_user(
        username=args.username,
        password=args.password,
        role=args.role,
        nickname=args.nickname,
        must_change_password=args.must_change_password,
        status=args.status,
    )
    print(f"Created account {args.username} with id={user_id}")


def import_csv(args):
    created = 0
    skipped = 0
    failed = 0
    with open(args.file, "r", encoding=args.encoding, newline="") as file:
        reader = csv.DictReader(file)
        required = {"username", "password", "role", "nickname", "must_change_password", "status"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"CSV missing columns: {', '.join(sorted(missing))}")

        for row in reader:
            username = (row.get("username") or "").strip()
            try:
                if not username:
                    skipped += 1
                    print("Skip row without username")
                    continue
                if get_user_by_username(username):
                    skipped += 1
                    print(f"Skip existing account: {username}")
                    continue
                create_user(
                    username=username,
                    password=row["password"],
                    role=row["role"],
                    nickname=row.get("nickname", ""),
                    must_change_password=parse_bool(row.get("must_change_password", "true")),
                    status=row.get("status", "active"),
                )
                created += 1
                print(f"Created account: {username}")
            except Exception as exc:
                failed += 1
                print(f"Failed account {username}: {exc}")

    print(f"Import finished: created={created}, skipped={skipped}, failed={failed}")


def reset_password(args):
    if not set_user_password(args.username, args.password, must_change_password=True):
        raise SystemExit(f"Account not found: {args.username}")
    print(f"Password reset for {args.username}. must_change_password=true")


def delete_account(args):
    if not delete_user(args.username):
        raise SystemExit(f"Account not found: {args.username}")
    print(f"Deleted account: {args.username}")


def clear_accounts(args):
    if not args.yes:
        raise SystemExit("Refusing to clear accounts without --yes")
    deleted = clear_users()
    print(f"Deleted {deleted} accounts.")


def update_account(args):
    if not update_user_fields(args.username, role=args.role, nickname=args.nickname, status=args.status):
        raise SystemExit(f"Account not found or no changes: {args.username}")
    print(f"Updated account: {args.username}")


def rename_account(args):
    if not rename_user(args.old_username, args.new_username):
        raise SystemExit(f"Account not found or no changes: {args.old_username}")
    print(f"Renamed account {args.old_username} -> {args.new_username}")


def build_parser():
    parser = argparse.ArgumentParser(description="Manage case library accounts")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all accounts").set_defaults(func=lambda args: print_users())

    create = sub.add_parser("create", help="Create one account")
    create.add_argument("--username", required=True)
    create.add_argument("--password", required=True)
    create.add_argument("--role", choices=["normal", "admin"], required=True)
    create.add_argument("--nickname", default="")
    create.add_argument("--must-change-password", type=parse_bool, default=True)
    create.add_argument("--status", choices=["active", "no_active"], default="active")
    create.set_defaults(func=create_account)

    bulk = sub.add_parser("import-csv", help="Import accounts from CSV")
    bulk.add_argument("--file", required=True)
    bulk.add_argument("--encoding", default="utf-8-sig")
    bulk.set_defaults(func=import_csv)

    reset = sub.add_parser("reset-password", help="Reset one account password")
    reset.add_argument("--username", required=True)
    reset.add_argument("--password", required=True)
    reset.set_defaults(func=reset_password)

    delete = sub.add_parser("delete", help="Delete one account")
    delete.add_argument("--username", required=True)
    delete.set_defaults(func=delete_account)

    clear = sub.add_parser("clear", help="Delete all accounts")
    clear.add_argument("--yes", action="store_true")
    clear.set_defaults(func=clear_accounts)

    update = sub.add_parser("update", help="Update role, nickname, or status")
    update.add_argument("--username", required=True)
    update.add_argument("--role", choices=["normal", "admin"])
    update.add_argument("--nickname")
    update.add_argument("--status", choices=["active", "no_active"])
    update.set_defaults(func=update_account)

    rename = sub.add_parser("rename", help="Rename username")
    rename.add_argument("--old-username", required=True)
    rename.add_argument("--new-username", required=True)
    rename.set_defaults(func=rename_account)

    return parser


def main():
    init_db()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
