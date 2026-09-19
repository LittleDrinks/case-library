#!/usr/bin/env python3
"""Failure-closed contracts for scripts/run-backend-mutation.sh.

Uses private fixtures and a fake ``python -m mutmut`` module. It never invokes
real mutation tooling or Docker.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts" / "run-backend-mutation.sh"

FAKE_MUTMUT = r'''
import json
import os
import sys
import time
from pathlib import Path

mode = os.environ.get("FAKE_MUTMUT_MODE", "success")
command = sys.argv[1] if len(sys.argv) > 1 else ""
log = os.environ.get("FAKE_MUTMUT_LOG")
if log:
    with open(log, "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"command": command, "args": sys.argv[2:]}) + "\n")
if command == "run":
    meta = Path("mutants/app/fake.py.meta")
    meta.parent.mkdir(parents=True, exist_ok=True)
    value = None if mode == "partial" else 1
    meta.write_text(json.dumps({"exit_code_by_key": {"fake": value}}), encoding="utf-8")
    if mode == "orphan":
        child = os.fork()
        if child == 0:
            import signal
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            Path("orphan-ready").write_text(json.dumps({"pid": os.getpid(), "start": Path(f"/proc/{os.getpid()}/stat").read_text().split()[21]}))
            while True:
                time.sleep(1)
        while not Path("orphan-ready").exists():
            time.sleep(0.01)
        Path("orphan-group").write_text(str(os.getpgrp()))
        raise SystemExit(7)
    if mode == "owner":
        Path("mutants/mutmut-cicd-stats.json").write_text("owner-report\n", encoding="utf-8")
        Path(os.environ["FAKE_MUTMUT_READY"]).touch()
        while not Path(os.environ["FAKE_MUTMUT_RELEASE"]).exists():
            time.sleep(0.01)
    raise SystemExit({"failure": 7, "exit2": 2}.get(mode, 0))
if command == "export-cicd-stats":
    if mode == "export-failure":
        Path("mutants/mutmut-cicd-stats.json").write_text("broken")
        raise SystemExit(9)
    if mode != "missing-report":
        Path("mutants/mutmut-cicd-stats.json").write_text(
            json.dumps({"total": 1, "killed": int(mode != "partial"), "survived": 0,
                        "no_tests": 0, "timeout": 0}) + "\n", encoding="utf-8"
        )
    raise SystemExit(0)
raise SystemExit(9)
'''


def fixture() -> tuple[Path, Path, Path]:
    root = Path(tempfile.mkdtemp(prefix="backend-mutation-wrapper-"))
    backend = root / "backend"
    backend.mkdir()
    (backend / "app").mkdir()
    (backend / "app/fake.py").write_text("def rule(): return True\n")
    (backend / "mutants").mkdir()
    (backend / "mutants" / "mutmut-cicd-stats.json").write_text("old-success\n", encoding="utf-8")
    (backend / "mutants" / "resume-marker").write_text("keep\n", encoding="utf-8")
    (root / "files").mkdir()
    (root / "scripts").mkdir()
    (root / ".env.example").write_text("TEST=1\n", encoding="utf-8")
    shutil.copy2(WRAPPER, root / "scripts" / "run-backend-mutation.sh")
    fake = root / "fake" / "mutmut"
    fake.mkdir(parents=True)
    (fake / "__init__.py").write_text("\n", encoding="utf-8")
    (fake / "__main__.py").write_text(FAKE_MUTMUT, encoding="utf-8")
    return root, backend, fake.parent


def run(root: Path, fake_root: Path, mode: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update(
        PYTHONPATH=str(fake_root),
        FAKE_MUTMUT_MODE=mode,
        FAKE_MUTMUT_LOG=str(root / "fake.log"),
    )
    return subprocess.run(
        ["bash", "scripts/run-backend-mutation.sh", *args],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )


def status(backend: Path) -> dict:
    return json.loads((backend / "mutants" / "mutmut-run-status.json").read_text())


def assert_links_clean(backend: Path) -> None:
    assert not any((backend / path).exists() or (backend / path).is_symlink()
                    for path in ("files", "scripts", ".env.example"))


def success_contract() -> None:
    root, backend, fake = fixture()
    try:
        result = run(root, fake, "success", "target-mutant")
        assert result.returncode == 0, result.stderr
        assert json.loads((backend / "mutants/mutmut-cicd-stats.json").read_text())["total"] == 1
        assert status(backend) == {
            "head": "unknown", "scope": "backend/app", "args": ["target-mutant"],
            "status": "completed", "exit": 0,
        }
        assert_links_clean(backend)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def failure_contract() -> None:
    root, backend, fake = fixture()
    try:
        result = run(root, fake, "failure")
        assert result.returncode == 7, result.stderr
        assert status(backend)["status"] == "failed"
        assert status(backend)["exit"] == 7
        assert not (backend / "mutants/mutmut-cicd-stats.json").exists()
        assert_links_clean(backend)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def fixture_collision_contract() -> None:
    root, backend, fake = fixture()
    try:
        (backend / "files").mkdir()
        result = run(root, fake, "success")
        assert result.returncode == 2
        assert not (backend / "mutants/mutmut-cicd-stats.json").exists()
        assert (backend / "mutants/resume-marker").read_text() == "keep\n"
        assert status(backend)["status"] == "failed"
        assert status(backend)["exit"] == 2
        assert not (root / "fake.log").exists()
        assert (backend / "files").is_dir()
        assert not (backend / "files").is_symlink()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def lock_contention_contract() -> None:
    root, backend, fake = fixture()
    ready = root / "owner-ready"
    try:
        owner_env = dict(
            PYTHONPATH=str(fake), FAKE_MUTMUT_MODE="owner",
            FAKE_MUTMUT_LOG=str(root / "owner.log"), FAKE_MUTMUT_READY=str(ready),
            FAKE_MUTMUT_RELEASE=str(root / "owner-release"),
        )
        owner = subprocess.Popen(
            ["bash", "scripts/run-backend-mutation.sh"], cwd=root,
            env={**os.environ, **owner_env}, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists(), owner.communicate(timeout=5)
        second = run(root, fake, "success")
        assert second.returncode == 2, second.stderr
        assert (backend / "mutants/mutmut-cicd-stats.json").read_text() == "owner-report\n"
        (root / "owner-release").touch()
        assert owner.wait(timeout=10) == 0
        assert status(backend)["status"] == "completed"
        assert_links_clean(backend)
    finally:
        if 'owner' in locals() and owner.poll() is None:
            owner.terminate()
            owner.wait(timeout=10)
        shutil.rmtree(root, ignore_errors=True)


def nonzero_exit_does_not_publish_cached_report_contract() -> None:
    root, backend, fake = fixture()
    try:
        result = run(root, fake, "exit2", "target-mutant")
        assert result.returncode == 2
        assert not (backend / "mutants/mutmut-cicd-stats.json").exists()
        assert status(backend)["status"] == "failed"
        assert status(backend)["exit"] == 2
        log_lines = [json.loads(line) for line in (root / "fake.log").read_text().splitlines()]
        assert log_lines == [{"command": "run", "args": ["--max-children", "1", "target-mutant"]}]
        assert_links_clean(backend)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def zero_exit_without_fresh_report_is_failure_contract() -> None:
    root, backend, fake = fixture()
    try:
        result = run(root, fake, "missing-report")
        assert result.returncode == 1
        assert not (backend / "mutants/mutmut-cicd-stats.json").exists()
        assert status(backend)["status"] == "failed"
        assert status(backend)["exit"] == 1
        assert_links_clean(backend)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def partial_and_export_failure_contracts() -> None:
    for mode, expected_exit, phase, published in (
        ("partial", 3, "partial", True),
        ("export-failure", 9, "failed", False),
    ):
        root, backend, fake = fixture()
        try:
            result = run(root, fake, mode)
            assert result.returncode == expected_exit, result.stderr
            assert status(backend)["status"] == phase
            assert status(backend)["exit"] == expected_exit
            assert (backend / "mutants/mutmut-cicd-stats.json").exists() == published
            assert_links_clean(backend)
        finally:
            shutil.rmtree(root, ignore_errors=True)


def retired_source_metadata_contract() -> None:
    root, backend, fake = fixture()
    try:
        retired = backend / "mutants/app/retired.py.meta"
        retired.parent.mkdir()
        retired.write_text(json.dumps({"exit_code_by_key": {"retired": None}}))
        result = run(root, fake, "success")
        assert result.returncode == 0, result.stderr
        assert status(backend)["status"] == "completed"
        assert retired.exists()
        assert_links_clean(backend)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def orphan_cleanup_contract() -> None:
    root, backend, fake = fixture()
    try:
        result = run(root, fake, "orphan")
        assert result.returncode == 7, result.stderr
        child = json.loads((backend / "orphan-ready").read_text())["pid"]
        stat = Path(f"/proc/{child}/stat")
        assert not stat.exists() or stat.read_text().split()[2] == "Z", "owned child remains running"
        assert status(backend)["status"] == "failed"
        assert status(backend)["exit"] == 7
        assert not (backend / "mutants/mutmut-cicd-stats.json").exists()
        assert_links_clean(backend)
    finally:
        ready = backend / "orphan-ready"
        if ready.exists():
            child = json.loads(ready.read_text())
            try:
                descriptor = os.pidfd_open(child["pid"])
            except ProcessLookupError:
                pass
            else:
                try:
                    stat = Path(f"/proc/{child['pid']}/stat")
                    if stat.exists() and stat.read_text().split()[21] == child["start"]:
                        signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                finally:
                    os.close(descriptor)
        shutil.rmtree(root, ignore_errors=True)


def main() -> None:
    orphan_cleanup_contract()
    success_contract()
    failure_contract()
    fixture_collision_contract()
    lock_contention_contract()
    nonzero_exit_does_not_publish_cached_report_contract()
    zero_exit_without_fresh_report_is_failure_contract()
    partial_and_export_failure_contracts()
    retired_source_metadata_contract()
    print("backend-mutation-wrapper-probe: failure-closed contracts pass")


if __name__ == "__main__":
    main()
