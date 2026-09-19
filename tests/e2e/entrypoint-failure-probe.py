#!/usr/bin/env python3
"""Whole-entrypoint failure probe: with a PATH shim standing in for Docker,
inject a failure at the mongo-init health wait (the last shared-setup
stage) and assert the runner performs only its owned teardown afterwards —
no run/up/build/pull (in particular no backend-e2e bucket-clear container)
after the failure. Never touches a real daemon."""
import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import tempfile

PROBE = pathlib.Path(tempfile.mkdtemp(prefix="e2e-probe-"))

project_dir = sys.argv[1]
runner = pathlib.Path(project_dir) / "scripts" / "run-e2e.sh"

tmp = tempfile.mkdtemp(prefix="e2e-failprobe-")
shim = pathlib.Path(tmp) / "docker"
shim.write_text(
    "#!/bin/sh\n"
    f'printf \'%s\\n\' "$*" >> {tmp}/docker-calls.log\n'
    "# Inject failure at the mongo replica-set health wait: this is the last\n"
    "  # shared-setup stage, so everything after it (mongo-init wait, database\n"
    "  # drop, suite up) is proven unreachable, and cleanup may only inspect.\n"
    "case \" $* \" in *' up -d --wait mongo-init'*) exit 37 ;; esac\n"
    "exit 0\n"
)
shim.chmod(shim.stat().st_mode | stat.S_IEXEC)

slug = re.sub(r"[^a-z0-9_-]", "-", pathlib.Path(project_dir).name.lower())
digest = __import__("hashlib").sha256(str(pathlib.Path(project_dir).resolve()).encode()).hexdigest()[:8]
lock_path = f"/tmp/case-library-e2e-{slug}-{digest}.lock"
# Never unlink the lock file: a live E2E run may own it, and deleting the
# inode would let two runners hold "the lock" concurrently. Stale locks from
# crashed probes are acceptable (flock is advisory and released on fd close).

env = dict(os.environ)
env["PATH"] = f"{tmp}:{env.get('PATH', '')}"
result = subprocess.run(
    ["/bin/sh", str(runner), "--backend"],
    capture_output=True,
    text=True,
    env=env,
    timeout=120,
)
lines = [l for l in pathlib.Path(tmp, "docker-calls.log").read_text().splitlines() if l.strip()]
# The injected failure happens at `compose up -d --wait mongo-init`. After it,
# cleanup may only run compose down / ps/volume/network inspections — never
# `run` (bucket clear), never build/pull.
failure_index = next(
    (i for i, l in enumerate(lines) if " up -d --wait mongo-init" in l), None
)
after = lines[failure_index + 1:] if failure_index is not None else []
forbidden_after = [
    l for l in after
    if re.search(r"\b(run|build|pull|push|up)\b", l)
]
report = {
    "exit": result.returncode,
    "docker_call_count": len(lines),
    "failure_stage_found": failure_index is not None,
    "calls_after_failure": after,
    "forbidden_after_failure": forbidden_after,
}
(PROBE / "entrypoint-failure-probe-internal.json").write_text(json.dumps(report, indent=2))
ok = (
    result.returncode != 0
    and report["failure_stage_found"]
    and not forbidden_after
)
print(json.dumps(report, indent=2))
sys.exit(0 if ok else 1)
