#!/usr/bin/env python3
"""Executable regression: a second run-e2e.sh invocation must exit 2 while
an exclusive lock is held by a first owner, and must perform ZERO Docker
mutations. A PATH shim records every docker invocation; the assertion is
that the list stays empty. This probe never touches a real daemon."""
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile

PROBE = pathlib.Path(tempfile.mkdtemp(prefix="e2e-probe-"))
project_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
runner = pathlib.Path(project_dir) / "scripts" / "run-e2e.sh"

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
lock_path = f"/tmp/case-library-e2e-{slug}-{digest}.lock"

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

report = {
    "exit": result.returncode,
    "expected_exit": 2,
    "stderr": result.stderr.strip(),
    "docker_calls": docker_calls.strip(),
    "docker_call_count": len([l for l in docker_calls.splitlines() if l.strip()]),
}
(PROBE / "lock-owner-probe-internal.json").write_text(json.dumps(report, indent=2))

ok = result.returncode == 2 and report["docker_call_count"] == 0
print(json.dumps(report, indent=2))
sys.exit(0 if ok else 1)
