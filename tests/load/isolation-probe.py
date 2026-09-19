"""Exercise the load entrypoint without contacting a Docker daemon."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(sys.argv[1]).resolve()
for project in ("case-library-load-proof-a", "case-library-load-proof-b"):
    env = dict(
        os.environ,
        COMPOSE_PROJECT_NAME=project,
        IMAGE_PREFIX=project,
        COMPOSE_FILE=f"{root}/docker-compose.yml:{root}/deploy/load.compose.yml",
    )
    config = json.loads(subprocess.check_output(
        ["docker", "compose", "--env-file", str(root / ".env.example"),
         "--profile", "load", "config", "--format", "json"],
        env=env, text=True,
    ))
    for name, service in config["services"].items():
        if name == "load" or name.startswith("load-"):
            assert service["image"].startswith(project + "-"), name
    for name in ("database", "load_test"):
        assert not config["networks"][name].get("ipam", {}).get("config"), name

with tempfile.TemporaryDirectory(prefix="load-isolation-") as temporary:
    fixture = Path(temporary)
    (fixture / "scripts").mkdir()
    for name in ("run-load.sh", "test-database.sh"):
        shutil.copy2(root / "scripts" / name, fixture / "scripts" / name)
    binary = fixture / "bin"
    binary.mkdir()
    shim = binary / "docker"
    shim.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
log = pathlib.Path(os.environ["LOAD_PROBE_LOG"])
first = not log.exists()
with log.open("a") as stream:
    stream.write(json.dumps({"args": sys.argv[1:], "project": os.environ.get("COMPOSE_PROJECT_NAME"), "image": os.environ.get("IMAGE_PREFIX")}) + "\\n")
sys.exit(37 if first else 0)
''')
    shim.chmod(0o755)
    log = fixture / "calls.jsonl"
    env = dict(os.environ, PATH=f"{binary}:{os.environ['PATH']}", LOAD_PROBE_LOG=str(log))
    result = subprocess.run(["sh", str(fixture / "scripts/run-load.sh")], env=env, capture_output=True, text=True, timeout=20)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert result.returncode == 37, result
    assert len(calls) == 5, calls
    project = calls[0]["project"]
    assert project and project.startswith("case-library-load-"), calls
    assert all(call["project"] == call["image"] == project for call in calls), calls
    for call in calls[:2]:
        args = call["args"]
        assert args[args.index("--project-name") + 1] == project, call
        assert "down" in args and "--volumes" in args and "--remove-orphans" in args, call
    for call, kind in zip(calls[2:], ("ps", "volume", "network")):
        assert call["args"][0] == kind, call
        assert f"label=com.docker.compose.project={project}" in call["args"], call
    print("load isolation: failure preserves status and tears down only owned resources")
