#!/usr/bin/env python3
"""Executable regression: a second run-e2e.sh invocation must exit 2 while
an exclusive lock is held by a first owner, and must perform ZERO Docker
mutations. A PATH shim records every docker invocation; the assertion is
that the list stays empty. This probe never touches a real daemon."""
import json
import shutil
import os
import pathlib
import stat
import subprocess
import sys
import tempfile

PROBE = pathlib.Path(tempfile.mkdtemp(prefix="e2e-probe-"))
project_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
suite = sys.argv[2] if len(sys.argv) > 2 else "e2e"
assert suite in {"e2e", "load"}
source_dir = pathlib.Path(project_dir)
fixture = PROBE / "checkout"
(fixture / "scripts").mkdir(parents=True)
for name in (f"run-{suite}.sh", "test-database.sh"):
    shutil.copy2(source_dir / "scripts" / name, fixture / "scripts" / name)
project_dir = str(fixture)
sentinel = fixture / "test-results" / "load-smoke.txt"
sentinel.parent.mkdir()
sentinel.write_text("active owner's evidence\n")
runner = pathlib.Path(project_dir) / "scripts" / f"run-{suite}.sh"

tmp = tempfile.mkdtemp(prefix="e2e-lockprobe-")
shim = pathlib.Path(tmp) / "docker"
shim.write_text(
    "#!/bin/sh\n"
    f'printf \'%s\\n\' "$*" >> {tmp}/docker-calls.log\n'
    "exit 0\n"
)
shim.chmod(shim.stat().st_mode | stat.S_IEXEC)

# Owner holds the lock through Python's fcntl on the same lock file the
# runner will derive; we learn the runner's lock path from its own logic:
# /tmp/case-library-e2e-<slug>-<hash>.lock where slug/hash come from the
# checkout dir. Compute it the same way.
import fcntl
import hashlib
import re

slug = re.sub(r"[^a-z0-9_-]", "-", os.path.basename(project_dir).lower())
digest = hashlib.sha256(project_dir.encode()).hexdigest()[:8]
lock_path = f"/tmp/case-library-{suite}-{slug}-{digest}.lock"

owner = open(lock_path, "w")
fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)

env = dict(os.environ)
env["PATH"] = f"{tmp}:{env.get('PATH', '')}"
result = subprocess.run(
    ["/bin/sh", str(runner)],
    capture_output=True,
    text=True,
    env=env,
    timeout=60,
)
calls = pathlib.Path(tmp, "docker-calls.log")
docker_calls = calls.read_text() if calls.exists() else ""
owner.close()
pathlib.Path(lock_path).unlink()

report = {
    "exit": result.returncode,
    "expected_exit": 2,
    "stderr": result.stderr.strip(),
    "docker_calls": docker_calls.strip(),
    "docker_call_count": len([l for l in docker_calls.splitlines() if l.strip()]),
    "owner_evidence_unchanged": sentinel.exists() and sentinel.read_text() == "active owner's evidence\n",
}
(PROBE / "lock-owner-probe-internal.json").write_text(json.dumps(report, indent=2))

ok = result.returncode == 2 and report["docker_call_count"] == 0 and report["owner_evidence_unchanged"]
print(json.dumps(report, indent=2))
shutil.rmtree(tmp)
shutil.rmtree(PROBE)
sys.exit(0 if ok else 1)
