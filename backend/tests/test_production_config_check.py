from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[2] / "scripts" / "validate_production_config.py"
DEMO_VALUES = {
    "APP_SECRET": "case-library-demo-app-secret",
    "MINIO_ROOT_USER": "case-library-demo",
    "MINIO_ROOT_PASSWORD": "case-library-demo-secret",
    "BACKUP_AGE_RECIPIENT": "age1qwsucmt40ee3ajudtf5fs6p5a2t9vuqtwh6u4skrsdnz2ulsk9ls7ju9em",
    "BACKUP_AGE_IDENTITY": "AGE-SECRET-KEY-1RVN72Z4VX3UKTDQMKDGQWTQDPCG0K2837ZENLFCUJWAD75P9JL0QH6UJWS",
}
PRODUCTION_VALUES = {
    "APP_SECRET": "jY7!sK2@vN9#qP4$wR8%xT3&cM6*eL1?zH5+",
    "MINIO_ROOT_USER": "production-admin",
    "MINIO_ROOT_PASSWORD": "N7!mQ2@xL9#vR4$k",
    "BACKUP_AGE_RECIPIENT": "age1csc90nu8zzj6y33nhxymyzepgdlgw2n744smmql8kryafvqk9pashrskxy",
    "BACKUP_AGE_IDENTITY": "AGE-SECRET-KEY-19EAYS8SNQ9QRDKLYR4SGYL3JDCSSJG5X5XXKH490C42F24VE0A5QPHKUL3",
}


def secret_files(tmp_path: Path, values: dict[str, str]) -> dict[str, str]:
    environment = {}
    for name in (
        "APP_SECRET",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "BACKUP_AGE_IDENTITY",
    ):
        path = tmp_path / name.lower()
        path.write_text(values[name], encoding="utf-8")
        environment[f"{name}_FILE"] = str(path)
    return environment


def fake_age_keygen(tmp_path: Path) -> Path:
    executable = tmp_path / "age-keygen"
    executable.write_text(
        "#!/bin/sh\nread -r identity\n"
        f"test \"$identity\" = '{PRODUCTION_VALUES['BACKUP_AGE_IDENTITY']}' || exit 1\n"
        f"printf '%s\\n' '{PRODUCTION_VALUES['BACKUP_AGE_RECIPIENT']}'\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    return executable


def invoke(
    tmp_path: Path,
    app_environment: str,
    values: dict[str, str],
    *,
    with_age=True,
):
    if with_age:
        fake_age_keygen(tmp_path)
    environment = {"PATH": str(tmp_path), "APP_ENV": app_environment}
    environment.update(secret_files(tmp_path, values))
    environment["BACKUP_AGE_RECIPIENT"] = values["BACKUP_AGE_RECIPIENT"]
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )


def production_values() -> dict[str, str]:
    return dict(PRODUCTION_VALUES)


def test_public_defaults_match_example_environment() -> None:
    values = {}
    for line in (SCRIPT.parents[1] / ".env.example").read_text().splitlines():
        name, separator, value = line.partition("=")
        if separator and name in DEMO_VALUES:
            values[name] = value
    assert values == DEMO_VALUES


def test_demo_environment_accepts_public_demo_values(tmp_path: Path) -> None:
    result = invoke(tmp_path, "demo", DEMO_VALUES)
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""


@pytest.mark.parametrize("unsafe_name", tuple(DEMO_VALUES))
def test_production_rejects_each_public_demo_value(
    tmp_path: Path,
    unsafe_name: str,
) -> None:
    values = production_values()
    values[unsafe_name] = DEMO_VALUES[unsafe_name]
    result = invoke(tmp_path, "production", values)
    assert result.returncode == 1
    assert result.stderr == f"Unsafe production configuration: {unsafe_name}\n"
    assert not any(value in result.stderr for value in DEMO_VALUES.values())


def test_production_accepts_replaced_secret_values(tmp_path: Path) -> None:
    result = invoke(tmp_path, "production", production_values())
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""


@pytest.mark.parametrize("app_secret", ["short-secret", "a" * 32])
def test_production_rejects_weak_app_secret(
    tmp_path: Path,
    app_secret: str,
) -> None:
    values = production_values()
    values["APP_SECRET"] = app_secret

    result = invoke(tmp_path, "production", values)

    assert result.returncode == 1
    assert result.stderr == "Unsafe production configuration: APP_SECRET\n"


@pytest.mark.parametrize("username", ["ab", "invalid user"])
def test_production_rejects_invalid_minio_user(
    tmp_path: Path,
    username: str,
) -> None:
    values = production_values()
    values["MINIO_ROOT_USER"] = username

    result = invoke(tmp_path, "production", values)

    assert result.returncode == 1
    assert result.stderr == "Unsafe production configuration: MINIO_ROOT_USER\n"


@pytest.mark.parametrize("password", ["short", "a" * 16])
def test_production_rejects_weak_minio_password(
    tmp_path: Path,
    password: str,
) -> None:
    values = production_values()
    values["MINIO_ROOT_PASSWORD"] = password

    result = invoke(tmp_path, "production", values)

    assert result.returncode == 1
    assert result.stderr == "Unsafe production configuration: MINIO_ROOT_PASSWORD\n"


def test_production_rejects_invalid_age_identity(tmp_path: Path) -> None:
    values = production_values()
    values["BACKUP_AGE_IDENTITY"] = "AGE-SECRET-KEY-INVALID"

    result = invoke(tmp_path, "production", values)

    assert result.returncode == 1
    assert result.stderr == "Unsafe production configuration: BACKUP_AGE_IDENTITY\n"


@pytest.mark.parametrize(
    "recipient", ["age1invalid", DEMO_VALUES["BACKUP_AGE_RECIPIENT"]]
)
def test_production_rejects_mismatched_age_recipient(
    tmp_path: Path,
    recipient: str,
) -> None:
    values = production_values()
    values["BACKUP_AGE_RECIPIENT"] = recipient

    result = invoke(tmp_path, "production", values)

    assert result.returncode == 1
    assert result.stderr == "Unsafe production configuration: BACKUP_AGE_RECIPIENT\n"


def test_production_fails_closed_without_age_keygen(tmp_path: Path) -> None:
    result = invoke(tmp_path, "production", production_values(), with_age=False)

    assert result.returncode == 1
    assert result.stderr == "Unsafe production configuration: BACKUP_AGE_IDENTITY\n"
