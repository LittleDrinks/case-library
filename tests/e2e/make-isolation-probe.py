"""Exercise Make prerequisites and demo targets without changing Docker state."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
DOCKER_SHIM = """#!/bin/sh
printf '%s|%s|%s\\n' "${COMPOSE_PROJECT_NAME-}" "${IMAGE_PREFIX-}" "$*" >> "$PROBE_LOG"
"""


def make_fixture(path: Path) -> dict[str, str]:
    (path / "scripts").mkdir(parents=True)
    (path / "bin").mkdir()
    for filename in ("Makefile", "scripts/ci-images.sh", ".env.example"):
        shutil.copy2(ROOT / filename, path / filename)
    shim = path / "bin/docker"
    shim.write_text(DOCKER_SHIM)
    shim.chmod(0o755)
    env = os.environ.copy()
    for key in ("COMPOSE_PROJECT_NAME", "IMAGE_PREFIX", "TEST_IMAGE_PREFIX", "MAKEFLAGS", "MFLAGS"):
        env.pop(key, None)
    env.update(PATH=f"{path / 'bin'}:{env['PATH']}", CI="", PROBE_LOG=str(path / "calls.log"))
    return env


def run_target(path: Path, env: dict[str, str], target: str) -> list[list[str]]:
    log = path / "calls.log"
    log.unlink(missing_ok=True)
    result = subprocess.run(
        ["make", target], cwd=path, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"{target}: {result.stdout}\n{result.stderr}"
    calls = [line.split("|", 2) for line in log.read_text().splitlines()]
    assert calls, f"{target} must invoke Compose"
    return calls


def test_identity(calls: list[list[str]], target: str) -> str:
    builds = [row for row in calls if " build " in f" {row[2]} "]
    runs = [row for row in calls if " run " in f" {row[2]} "]
    assert builds and len(runs) >= 2, f"{target} must build, check its gate, and test"
    prefix = builds[0][1]
    assert re.fullmatch(r"[a-z0-9][a-z0-9_-]*", prefix), f"invalid image prefix: {prefix}"
    assert prefix != "case-library-v2", "tests must not use the demo image prefix"
    for project, image, command in builds + runs:
        assert image == prefix, f"{target} mixes image prefixes: {image!r}, {prefix!r}"
        assert f"--project-name {prefix} " in command, f"{target} mixes Compose projects"
        assert project in ("", prefix), f"{target} exports a conflicting project"
    return prefix


def main() -> None:
    identities = []
    with tempfile.TemporaryDirectory(prefix="case-library-make-probe-") as directory:
        for parent in ("one", "two"):
            path = Path(directory) / parent / ".checkout"
            env = make_fixture(path)
            backend = test_identity(run_target(path, env, "test-backend"), "test-backend")
            frontend = test_identity(run_target(path, env, "test-frontend"), "test-frontend")
            assert backend == frontend, "test targets must share one checkout identity"
            identities.append(backend)
            for target in ("up", "down"):
                for project, image, command in run_target(path, env, target):
                    assert not project and not image, f"{target} exports test identity"
                    assert "--project-name" not in command, f"{target} overrides demo project"
        assert identities[0] != identities[1], "same-named checkouts share test images"
    print("make-isolation-probe: test gates, test runs, and demo targets are isolated")


if __name__ == "__main__":
    main()
