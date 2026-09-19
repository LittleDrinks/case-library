#!/usr/bin/env python3
"""Whole-entrypoint failure probes against a private minimal fixture
checkout (its own copy of the runner and overlay), driven through a PATH
docker shim. Never touches a real daemon or the real checkout's lock (the
fixture's project name derives from the fixture path, so its lock file is
distinct).

Probes:
1. first-e2e-app-failure — `compose ... up -d --wait e2e-app` is injected
   to exit 37. Required: runner exit exactly 37 AND afterwards the actual
   owned teardown (exactly one `down --volumes --remove-orphans` plus the
   three inventory inspections) with no other calls.
2. hup-during-suite — no injected failure; the runner reaches the e2e-app
   stage, a gate holds it while the parent confirms readiness and sends
   SIGHUP. Required: exit exactly 129 AND the same owned teardown, even
   after a second HUP/TERM/INT during cleanup.
3. old-signal-trap counter-example — restoring the old signal handlers
   must fail the same blocked-cleanup probe.
4. trap-regression counter-example — with the runner's cleanup trap
   deleted (sed on the fixture copy), the HUP probe MUST fail; proves the
   probe is red against a cleanup-less runner.
"""
import hashlib
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

PROBE = pathlib.Path(tempfile.mkdtemp(prefix="e2e-probe-"))
REAL = pathlib.Path(sys.argv[1]).resolve()
tmp = pathlib.Path(tempfile.mkdtemp(prefix="e2e-failprobe-"))
fixture = tmp / "checkout"


def make_fixture():
    fixture.mkdir()
    for rel in ("scripts/run-e2e.sh", "scripts/ci-images.sh",
                "scripts/test-database.sh", "deploy/e2e.compose.yml",
                "docker-compose.yml", ".env.example"):
        src = REAL / rel
        dst = fixture / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    # Minimal stand-in build inputs: every Dockerfile the fixture's compose
    # file references must exist for fingerprint parsing, but they only need
    # to be syntactically plausible for the shim path (no real build runs).
    (fixture / "backend.Dockerfile").write_text(
        "FROM alpine:3\nCOPY backend/app ./app\nCOPY backend/tests ./tests\n"
    )
    (fixture / "frontend.Dockerfile").write_text("FROM alpine:3\n")
    (fixture / "deploy" / "e2e.Dockerfile").write_text("FROM alpine:3\n")
    (fixture / "deploy" / "fake-openai.Dockerfile").write_text("FROM alpine:3\n")
    (fixture / "deploy" / "meilisearch.Dockerfile").write_text("FROM alpine:3\n")
    (fixture / "deploy" / "mongo-init.Dockerfile").write_text(
        "FROM alpine:3\nCOPY scripts/mongo-init.sh /usr/local/bin/mongo-init\n"
    )
    (fixture / "scripts" / "mongo-init.sh").write_text("#!/bin/sh\nexit 0\n")
    (fixture / "backend" / "app").mkdir(parents=True, exist_ok=True)
    (fixture / "backend" / "tests").mkdir(parents=True, exist_ok=True)
    (fixture / "backend" / "app" / "__init__.py").write_text("")
    (fixture / "backend" / "tests" / "pytest.ini").write_text("")
    (fixture / "test-results").mkdir()


FIXTURE_CONFIG = (
    '{"services": {'
    '"e2e-app": {"build": {"dockerfile": "backend.Dockerfile", "target": "runtime"}},'
    '"backend-e2e": {"build": {"dockerfile": "backend.Dockerfile", "target": "test"}},'
    '"e2e": {"build": {"dockerfile": "deploy/e2e.Dockerfile"}},'
    '"e2e-frontend": {"build": {"dockerfile": "frontend.Dockerfile"}},'
    '"e2e-ai-provider": {"build": {"dockerfile": "deploy/fake-openai.Dockerfile"}},'
    '"e2e-meilisearch": {"build": {"dockerfile": "deploy/meilisearch.Dockerfile"}},'
    '"mongo-init": {"build": {"dockerfile": "deploy/mongo-init.Dockerfile"}},'
    '"production-config-check": {"build": {"dockerfile": "backend.Dockerfile", "target": "production-config-check"}}'
    '}}'
)

GATE_STAGE = "' up -d --wait e2e-app'"


def write_shim(fail_stage=None, gate=False):
    """fail_stage: docker call whose invocation exits 37. gate: hold inside
    the e2e-app stage until a release file appears (for HUP timing)."""
    shim = tmp / "docker"
    log = tmp / "docker-calls.log"
    for path in (log, *(tmp / name for name in (
        "at-gate", "release", "cleanup-gate", "cleanup-release",
    ))):
        path.unlink(missing_ok=True)
    fail_case = ""
    if fail_stage:
        pattern = {
            "e2e-app": GATE_STAGE,
            "mongo-init": "' up -d --wait mongo-init'",
        }[fail_stage]
        fail_case = f'case " $* " in *{pattern}*) exit 37 ;; esac\n'
    gate_case = ""
    if gate:
        gate_case = (
            'case " $* " in *' + GATE_STAGE + "*)\n"
            f'  touch "{tmp}/at-gate"\n'
            f'  while test ! -e "{tmp}/release"; do sleep 0.05; done\n'
            ";; esac\n"
            'case " $* " in *" down --volumes --remove-orphans "*)\n'
            f'  if test -e "{tmp}/at-gate"; then\n'
            f'    touch "{tmp}/cleanup-gate"\n'
            f'    while test ! -e "{tmp}/cleanup-release"; do sleep 0.05; done\n'
            '  fi\n'
            ";; esac\n"
        )
    shim.write_text(
        "#!/bin/sh\n"
        f'printf \'%s\\n\' "$*" >> {log}\n'
        "# compose config must answer valid JSON for fingerprint parsing.\n"
        'case " $* " in *" config --format json"*)\n'
        f"  printf '%s\\n' '{FIXTURE_CONFIG}'\n"
        "  exit 0 ;; esac\n"
        # drop_test_database reads "false" from mongosh.
        'case " $* " in *"exec -T mongo1 mongosh"*) printf \'false\\n\'; exit 0 ;; esac\n'
        # verify_mongo_project_ownership needs a container id for mongo1.
        'case " $* " in *" ps -q mongo1"*) printf \'fixture-mongo1-id\\n\'; exit 0 ;; esac\n'
        # ...and the inspect must report the owning project label.
        'case " $* " in *" inspect "--*) printf \'%s\\n\' "$COMPOSE_PROJECT_NAME"; exit 0 ;; esac\n'
        + fail_case
        + gate_case
        + "exit 0\n"
    )
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)


def teardown_shape(lines, after_stage):
    """After the stage call, require the actual owned teardown: exactly one
    compose down --volumes --remove-orphans then exactly the three inventory
    inspections (ps/volume/network). Anything else, or nothing, fails."""
    stages = [i for i, line in enumerate(lines) if after_stage in line]
    if not stages:
        return False, "stage call not found"
    idx = stages[-1]
    owner_match = re.search(r"--project-name ([^ ]+)", lines[idx])
    if not owner_match:
        return False, "stage project not found"
    owner = owner_match.group(1)
    rest = lines[idx + 1:]
    downs = [l for l in rest if "down --volumes --remove-orphans" in l]
    inspections = [l for l in rest if re.match(r"^(ps|volume|network) ", l)]
    problems = []
    if len(downs) != 1:
        problems.append(f"expected exactly 1 owned down, saw {len(downs)}")
    elif not re.search(r"--project-name " + re.escape(owner) + r"(?: |$)", downs[0]):
        problems.append("teardown project differs from stage owner")
    if downs and rest[0] != downs[0]:
        problems.append("inventory inspection precedes teardown")
    if len(inspections) != 3:
        problems.append(f"expected 3 inventory inspections, saw {len(inspections)}")
    else:
        kinds = [l.split(" ", 1)[0] for l in inspections]
        if sorted(kinds) != ["network", "ps", "volume"]:
            problems.append(f"inventory inspections not ps+volume+network: {kinds}")
        projects = set()
        for l in inspections:
            m = re.search(r"label=com\.docker\.compose\.project=([^ ]+)", l)
            if m:
                projects.add(m.group(1))
        if projects != {owner} or any(
            f"label=com.docker.compose.project={owner}" not in line
            for line in inspections
        ):
            problems.append(f"inventory inspections disagree on project: {projects}")
    leftover = [l for l in rest if l not in downs and l not in inspections]
    if leftover:
        problems.append(f"unexpected calls after failure: {leftover}")
    return (not problems), "; ".join(problems)


def spawn():
    env = dict(os.environ)
    env["PATH"] = f"{tmp}:{env.get('PATH', '')}"
    return subprocess.Popen(
        ["/bin/sh", str(fixture / "scripts" / "run-e2e.sh"), "--backend"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
        cwd=str(fixture), start_new_session=True,
    )


def wait_for_call(proc, needle, timeout=90):
    """Poll the shim log until `needle` appears or the process exits; raise
    on timeout instead of waiting forever."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        log = tmp / "docker-calls.log"
        if log.exists():
            if any(needle in l for l in log.read_text().splitlines()):
                return
        if proc.poll() is not None:
            raise RuntimeError(f"runner exited {proc.returncode} before {needle}")
        time.sleep(0.05)
    raise RuntimeError(f"timeout waiting for {needle}")


def read_calls():
    log = tmp / "docker-calls.log"
    if not log.exists():
        return []
    return [l for l in log.read_text().splitlines() if l.strip()]


def verdict(label, rc, lines, expect_rc, after_stage):
    ok_shape, problem = teardown_shape(lines, after_stage)
    ok = rc == expect_rc and ok_shape
    report = {"label": label, "exit": rc, "expected_exit": expect_rc,
              "docker_calls": len(lines), "teardown_ok": ok_shape,
              "teardown_problem": problem}
    (PROBE / f"{label}.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    return ok


import signal as _signal

results = []
make_fixture()

def gate_ready(proc, timeout=30, name="at-gate"):
    gate = tmp / name
    deadline = time.time() + timeout
    while time.time() < deadline and not gate.exists():
        if proc.poll() is not None:
            raise RuntimeError(f"runner exited {proc.returncode} before gate")
        time.sleep(0.05)
    if not gate.exists():
        raise RuntimeError("gate never reached")
    return gate

# Probe 1: failure at the FIRST e2e-app start (suite stage).
write_shim(fail_stage="e2e-app")
proc = None
try:
    proc = spawn()
    wait_for_call(proc, "up -d --wait e2e-app")
    rc = proc.wait(timeout=120)
finally:
    lines = read_calls()
ok1 = verdict("first-e2e-app-failure", rc, lines, 37, "up -d --wait e2e-app")
results.append(ok1)

def repeated_cleanup_signals():
    write_shim(gate=True)
    proc = spawn()
    try:
        gate_ready(proc)
        os.killpg(proc.pid, _signal.SIGHUP)
        (tmp / "release").write_text("")
        gate_ready(proc, name="cleanup-gate")
        for signal in (_signal.SIGHUP, _signal.SIGTERM, _signal.SIGINT):
            try:
                os.killpg(proc.pid, signal)
            except ProcessLookupError:
                break
        (tmp / "cleanup-release").write_text("")
        return proc.wait(timeout=30), read_calls()
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, _signal.SIGKILL)
            proc.wait()


# The cleanup gate cannot be reached by the initial preclean invocation.
rc, lines = repeated_cleanup_signals()
ok2 = verdict("hup-during-suite-repeated-signals", rc, lines, 129, "up -d --wait e2e-app")
results.append(ok2)

runner = fixture / "scripts" / "run-e2e.sh"
fixed_runner = runner.read_text()
old_runner = fixed_runner.replace("trap - EXIT\n  trap '' INT TERM HUP", "trap - EXIT INT TERM")
assert old_runner != fixed_runner
runner.write_text(old_runner)
rc, lines = repeated_cleanup_signals()
ok_shape, problem = teardown_shape(lines, "up -d --wait e2e-app")
report = {"label": "old-signal-trap-control", "exit": rc,
          "teardown_ok": ok_shape, "teardown_problem": problem,
          "detected_regression": not ok_shape}
print(json.dumps(report))
results.append(not ok_shape)
runner.write_text(fixed_runner)

# Probe 3 (negative control): delete the runner's cleanup traps; the HUP
# probe must turn red (exit not 129 or teardown missing).
write_shim(gate=True)
subprocess.run(
    ["sed", "-i", "/^trap cleanup EXIT$/d; /^trap 'exit 130' INT$/d; "
     "/^trap 'exit 143' TERM$/d; /^trap 'exit 129' HUP$/d",
     str(fixture / "scripts" / "run-e2e.sh")],
    check=True,
)
proc = None
try:
    proc = spawn()
    wait_for_call(proc, "up -d --wait e2e-app")
    gate_ready(proc)
    os.killpg(proc.pid, _signal.SIGHUP)
    (tmp / "release").write_text("")
    rc = proc.wait(timeout=120)
finally:
    lines = read_calls()
    if proc and proc.poll() is None:
        proc.kill()
        proc.wait()
ok_shape, _ = teardown_shape(lines, "up -d --wait e2e-app")
ok3 = rc == -_signal.SIGHUP and not ok_shape
report = {"label": "trap-regression-control", "exit": rc,
          "teardown_ok": ok_shape, "detected_regression": ok3}
(PROBE / "trap-regression-control.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report))
results.append(ok3)

stage = "compose --project-name isolated up -d --wait e2e-app"
inventories = [
    f"{kind} --filter label=com.docker.compose.project=isolated"
    for kind in ("ps", "volume", "network")
]
wrong_owner = [stage, "compose --project-name case-library-v2 down --volumes --remove-orphans", *inventories]
results.append(not teardown_shape(wrong_owner, "up -d --wait e2e-app")[0])
wrong_order = [stage, *inventories, "compose --project-name isolated down --volumes --remove-orphans"]
results.append(not teardown_shape(wrong_order, "up -d --wait e2e-app")[0])

shutil.rmtree(tmp, ignore_errors=True)
shutil.rmtree(PROBE, ignore_errors=True)
sys.exit(0 if all(results) else 1)
