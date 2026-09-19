#!/usr/bin/env python3
"""Exercise run-load cleanup with repeated signals and a fake Docker CLI.

The probe owns a private fixture checkout, blocks the main mongo-init call, then
releases it after HUP so the real EXIT cleanup reaches a second, cleanup-only
down gate. HUP/TERM/INT are delivered while that down call is blocked. A
fixture with the old signal trap is required to fail the same assertion.
"""
from __future__ import annotations

import json
import os
import pathlib
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

REAL = pathlib.Path(sys.argv[1]).resolve()
ROOT = pathlib.Path(tempfile.mkdtemp(prefix="load-signal-probe-"))


def make_fixture(name: str, restore_old_trap: bool) -> dict[str, pathlib.Path]:
    work = ROOT / name
    fixture = work / "checkout"
    (fixture / "scripts").mkdir(parents=True)
    (fixture / "tests" / "load").mkdir(parents=True)
    for relative in ("scripts/run-load.sh", "scripts/test-database.sh"):
        destination = fixture / relative
        shutil.copy2(REAL / relative, destination)
    if restore_old_trap:
        runner = fixture / "scripts/run-load.sh"
        runner.write_text(
            runner.read_text().replace("  trap '' INT TERM HUP\n", "  trap - EXIT INT TERM HUP\n"),
        )
    for relative in ("seed-materials.js", "catalog-gate.js"):
        (fixture / "tests" / "load" / relative).write_text("\n")
    for relative in ("backend-distribution.sh", "upstream-keepalive.sh"):
        script = fixture / "tests" / "load" / relative
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    (fixture / ".env.example").write_text("\n")
    (fixture / "test-results").mkdir()
    paths = {"work": work, "fixture": fixture}
    for key in ("calls", "down_count", "main_gate", "main_release", "cleanup_gate", "cleanup_release", "cleanup_done"):
        paths[key] = work / key
    return paths


def write_docker(paths: dict[str, pathlib.Path]) -> None:
    q = lambda path: shlex.quote(str(path))
    paths["docker"] = paths["work"] / "docker"
    paths["docker"].write_text(
        "#!/bin/sh\n"
        "trap '' HUP TERM INT\n"
        f"printf '%s\\n' \"$*\" >> {q(paths['calls'])}\n"
        "case \" $* \" in\n"
        f"  *\" down --volumes --remove-orphans \"*)\n"
        f"    count=$(cat {q(paths['down_count'])} 2>/dev/null || printf 0)\n"
        "    count=$((count + 1))\n"
        f"    printf '%s\\n' \"$count\" > {q(paths['down_count'])}\n"
        f"    if test \"$count\" -eq 2; then touch {q(paths['cleanup_gate'])}; while test ! -e {q(paths['cleanup_release'])}; do sleep 0.02; done; touch {q(paths['cleanup_done'])}; fi\n"
        "    exit 0 ;;\n"
        f"  *\" up -d --wait mongo-init \"*) touch {q(paths['main_gate'])}; while test ! -e {q(paths['main_release'])}; do sleep 0.02; done; exit 0 ;;\n"
        "  *\"exec -T mongo1 mongosh \"*)\n"
        "    case \"$*\" in\n"
        "      *search_catalog_generation*) printf '%s\\n' 'catalog-index catalog-generation catalog-epoch' ;;\n"
        "      *countDocuments*) printf '%s\\n' '12480 12480 0 0 0' ;;\n"
        "    esac; exit 0 ;;\n"
        "  *\"ps --status running -q load-search-worker\"*) printf '%s\\n' worker-id; exit 0 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    paths["docker"].chmod(paths["docker"].stat().st_mode | stat.S_IEXEC)


def wait_for(path: pathlib.Path, process: subprocess.Popen[str], label: str) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            raise RuntimeError(f"runner exited before {label}: {process.returncode}")
        time.sleep(0.02)
    raise RuntimeError(f"timeout waiting for {label}")


def send_group(process: subprocess.Popen[str], sig: signal.Signals) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass


def cleanup_shape(paths: dict[str, pathlib.Path]) -> tuple[bool, dict]:
    lines = [line for line in paths["calls"].read_text().splitlines() if line.strip()]
    downs = [index for index, line in enumerate(lines) if "down --volumes --remove-orphans" in line]
    tail = lines[downs[-1] + 1 :] if downs else []
    inventory = [line for line in tail if line.startswith(("ps ", "volume ", "network "))]
    result = {
        "down_count": len(downs),
        "inventory": [line.split(" ", 1)[0] for line in inventory],
        "cleanup_done": paths["cleanup_done"].exists(),
    }
    result["ok"] = (
        len(downs) == 2
        and result["inventory"] == ["ps", "volume", "network"]
        and result["cleanup_done"]
    )
    return result["ok"], result


def run_case(name: str, restore_old_trap: bool) -> dict:
    paths = make_fixture(name, restore_old_trap)
    write_docker(paths)
    env = dict(os.environ, PATH=f"{paths['work']}:{os.environ.get('PATH', '')}", SKIP_BUILD="true")
    process = subprocess.Popen(
        ["/bin/sh", str(paths["fixture"] / "scripts/run-load.sh"), "smoke"],
        cwd=paths["fixture"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        wait_for(paths["main_gate"], process, "main run gate")
        send_group(process, signal.SIGHUP)
        paths["main_release"].touch()
        wait_for(paths["cleanup_gate"], process, "cleanup down gate")
        send_group(process, signal.SIGHUP)
        send_group(process, signal.SIGTERM)
        send_group(process, signal.SIGINT)
        paths["cleanup_release"].touch()
        returncode = process.wait(timeout=20)
    finally:
        send_group(process, signal.SIGKILL)
        if process.poll() is None:
            process.wait()
    shape_ok, shape = cleanup_shape(paths)
    return {"name": name, "old_trap": restore_old_trap, "exit": returncode, "shape": shape, "ok": returncode == 129 and shape_ok}


try:
    results = [run_case("fixed", False), run_case("old-trap", True)]
    print(json.dumps({"fixed": results[0], "old_trap_negative_control": results[1]}, ensure_ascii=False))
    sys.exit(0 if results[0]["ok"] and not results[1]["ok"] else 1)
finally:
    shutil.rmtree(ROOT)
