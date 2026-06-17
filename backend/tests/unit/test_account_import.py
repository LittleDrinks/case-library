#!/usr/bin/env python3
"""Unit checks for back-office account import helpers."""

from __future__ import annotations

import os
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

os.environ["MONGODB_DB_NAME"] = f"case_library_test_account_import_{uuid4().hex[:8]}"

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

ACCOUNT_ADMIN_PATH = BACKEND_DIR / "scripts" / "account_admin.py"
spec = spec_from_file_location("account_admin", ACCOUNT_ADMIN_PATH)
assert spec is not None
assert spec.loader is not None
account_admin = module_from_spec(spec)
sys.modules[spec.name] = account_admin
spec.loader.exec_module(account_admin)


def test_import_header_validation_accepts_school_identity_columns():
    errors = account_admin.validate_import_file_headers(
        ["school_id", "display_name", "role", "department"]
    )

    assert errors == []


def test_import_plan_normalizes_school_id_role_and_metadata_warning():
    rows = [
        {
            "school_id": "S10001",
            "display_name": "测试教师",
            "role": "user",
            "department": "测试学院",
            "must_change_password": "否",
        }
    ]

    parsed_rows, errors, summary = account_admin.build_import_plan(
        rows,
        default_password="temporary-pass-123",
        missing_password="error",
    )

    assert errors == []
    assert summary.as_dict() == {
        "total_rows": 1,
        "valid_rows": 1,
        "would_create": 0,
        "created": 0,
        "skipped_existing": 0,
        "errors": 0,
        "generated_passwords": 0,
    }
    assert parsed_rows[0].username == "S10001"
    assert parsed_rows[0].source_identity == "school_id"
    assert parsed_rows[0].role == "normal"
    assert parsed_rows[0].nickname == "测试教师"
    assert parsed_rows[0].must_change_password is False
    assert parsed_rows[0].ignored_columns == ["department"]


def test_import_plan_reports_row_errors_and_duplicate_usernames():
    rows = [
        {
            "username": "10001",
            "nickname": "教师一",
            "role": "normal",
            "password": "temporary-pass-123",
        },
        {
            "school_id": "10001",
            "name": "教师二",
            "role": "admin",
            "password": "temporary-pass-456",
        },
        {"username": "", "nickname": "教师三", "role": "guest", "password": "short"},
    ]

    parsed_rows, errors, summary = account_admin.build_import_plan(
        rows,
        default_password=None,
        missing_password="error",
    )

    assert [row.username for row in parsed_rows] == ["10001"]
    assert summary.errors == 2
    assert "duplicate username in import file: 10001" in errors[0]
    assert "missing username or school_id" in errors[1]
    assert "invalid role: guest" in errors[1]
    assert "password must be at least 8 characters" in errors[1]


def test_import_generates_temporary_password_without_printing(monkeypatch, tmp_path, capsys):
    import_file = tmp_path / "users.csv"
    import_file.write_text(
        "school_id,display_name,role\nS10001,测试教师,normal\n",
        encoding="utf-8",
    )
    generated_password = "generated-pass-should-not-print"
    created = []

    monkeypatch.setattr(account_admin, "init_db", lambda: None)
    monkeypatch.setattr(account_admin, "get_user_by_username", lambda username: None)
    monkeypatch.setattr(
        account_admin,
        "generate_import_password",
        lambda: generated_password,
    )
    monkeypatch.setattr(account_admin, "create_user", lambda **kwargs: created.append(kwargs))

    args = SimpleNamespace(
        file=str(import_file),
        encoding="utf-8",
        dry_run=True,
        missing_password="generate",
        default_password_env=None,
    )

    account_admin.import_users(args)

    output = capsys.readouterr().out
    assert created == []
    assert "Would create account: S10001" in output
    assert "generated temporary passwords were stored" not in output
    assert generated_password not in output
    assert "generated_passwords=1" in output


def test_import_skips_existing_accounts(monkeypatch, tmp_path, capsys):
    import_file = tmp_path / "users.csv"
    import_file.write_text(
        "username,nickname,role,password\n10001,测试教师,admin,temporary-pass-123\n",
        encoding="utf-8",
    )
    created = []

    monkeypatch.setattr(account_admin, "get_user_by_username", lambda username: {"username": username})
    monkeypatch.setattr(account_admin, "create_user", lambda **kwargs: created.append(kwargs))

    args = SimpleNamespace(
        file=str(import_file),
        encoding="utf-8",
        dry_run=False,
        missing_password="error",
        default_password_env=None,
    )

    account_admin.import_users(args)

    output = capsys.readouterr().out
    assert created == []
    assert "Skip existing account: 10001" in output
    assert "created=0" in output
    assert "skipped_existing=1" in output


def test_import_does_not_partially_create_when_rows_have_errors(
    monkeypatch, tmp_path, capsys
):
    import_file = tmp_path / "users.csv"
    import_file.write_text(
        "\n".join(
            [
                "username,nickname,role,password",
                "10001,测试教师,admin,temporary-pass-123",
                "10002,错误角色,guest,temporary-pass-456",
            ]
        ),
        encoding="utf-8",
    )
    created = []

    monkeypatch.setattr(account_admin, "get_user_by_username", lambda username: None)
    monkeypatch.setattr(account_admin, "create_user", lambda **kwargs: created.append(kwargs))

    args = SimpleNamespace(
        file=str(import_file),
        encoding="utf-8",
        dry_run=False,
        missing_password="error",
        default_password_env=None,
    )

    with pytest.raises(SystemExit) as exc_info:
        account_admin.import_users(args)

    output = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert created == []
    assert "Import error: Row 3: invalid role: guest" in output
    assert "Would create account: 10001" in output
    assert "created=0" in output
    assert "would_create=1" in output


def test_xlsx_rows_are_read_from_first_sheet(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    import_file = tmp_path / "users.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["school_id", "display_name", "role", "password"])
    sheet.append(["S10001", "测试教师", "normal", "temporary-pass-123"])
    workbook.save(import_file)

    rows, fieldnames = account_admin.read_import_rows(import_file, encoding="utf-8")

    assert fieldnames == ["school_id", "display_name", "role", "password"]
    assert rows == [
        {
            "school_id": "S10001",
            "display_name": "测试教师",
            "role": "normal",
            "password": "temporary-pass-123",
        }
    ]


def test_header_errors_exit_before_database_writes(monkeypatch, tmp_path, capsys):
    import_file = tmp_path / "users.csv"
    import_file.write_text("username,password\n10001,temporary-pass-123\n", encoding="utf-8")

    monkeypatch.setattr(
        account_admin,
        "get_user_by_username",
        lambda username: pytest.fail("database should not be queried"),
    )

    args = SimpleNamespace(
        file=str(import_file),
        encoding="utf-8",
        dry_run=True,
        missing_password="error",
        default_password_env=None,
    )

    with pytest.raises(SystemExit) as exc_info:
        account_admin.import_users(args)

    output = capsys.readouterr().out
    assert exc_info.value.code == 2
    assert "missing nickname, display_name, or name column" in output
    assert "missing role column" in output
