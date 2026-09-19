"""Exercise real runner functions against a Compose output-directory stand-in."""
from pathlib import Path
import os
import json
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
runner = (root / "scripts/run-e2e.sh").read_text()
names = (
    "run_browser_tests", "run_bdd_browser_tests", "run_agent_browser_tests",
    "run_sidebar_browser_tests", "run_tracer_browser_tests", "run_browser_suite",
)
functions = "\n".join(
    re.search(rf"^{name}\(\) \{{\n.*?^\}}", runner, re.M | re.S)[0]
    for name in names
)
shim = '''#!/usr/bin/env python3
import os
import json
from pathlib import Path
import shutil
import sys
args = sys.argv[1:]
with open(os.environ["PHASE_LOG"], "a") as stream:
    stream.write(json.dumps(args) + "\\n")
if "run" not in args:
    sys.exit(0)
mount = Path(args[args.index("-v") + 1].split(":", 1)[0])
# Playwright clears outputDir before running even when zero tests are selected.
if mount.exists():
    shutil.rmtree(mount)
mount.mkdir(parents=True)
(mount / "report.json").write_text("{}")
if "test:e2e:bdd" in args:
    (mount / "cucumber-report").mkdir()
    (mount / "cucumber-report/report.json").write_text("[]")
    sys.exit(int(os.environ.get("BDD_EXIT", "0")))
if "agent-e2e" in args:
    sys.exit(int(os.environ.get("AGENT_EXIT", "0")))
'''
with tempfile.TemporaryDirectory(prefix="browser-report-probe-") as tmp:
    directory = Path(tmp)
    compose = directory / "compose"
    compose.write_text(shim)
    compose.chmod(0o755)
    script = "set -eu\nstart_agent_app() { compose legacy-agent-start; }\nclear_e2e_bucket() { :; }\n"
    script += functions + '\nrun_browser_suite\n'
    for expected_status in (0, 42, 43):
        artifacts = directory / f"artifacts-{expected_status}"
        env = dict(os.environ, PATH=f"{directory}:{os.environ['PATH']}",
                   PHASE_LOG=str(directory / "phase.jsonl"), artifact_dir=str(artifacts), browser_spec="", BDD_EXIT="42" if expected_status == 42 else "0",
                   AGENT_EXIT="43" if expected_status == 43 else "0")
        (directory / "phase.jsonl").write_text("")
        result = subprocess.run(["sh", "-c", script], env=env, check=False)
        assert result.returncode == expected_status, (expected_status, result.returncode)
        assert (artifacts / "generic/report.json").is_file()
        assert (artifacts / "bdd/cucumber-report/report.json").is_file()
        calls = [json.loads(line) for line in (directory / "phase.jsonl").read_text().splitlines()]
        assert not any("legacy-agent-start" in call or "agent-e2e-loser" in call for call in calls)
        for call in calls:
            if "run" in call and ("agent-e2e" in call or "agent-tracer" in call):
                assert "--no-deps" in call, call
        if expected_status == 0:
            stages = []
            for call in calls:
                if "run" in call:
                    stages.append(Path(call[call.index("-v") + 1].split(":")[0]).name)
                elif "rm" in call:
                    stages.append("remove:" + ",".join(call[call.index("-sf") + 1:]))
                elif "up" in call:
                    stages.append("start:" + call[call.index("--wait") + 1])
            assert stages == [
                "start:e2e-frontend", "generic", "bdd", "remove:e2e-app,e2e-frontend",
                "start:agent-e2e-gateway", "agent",
                "remove:agent-e2e-gateway,agent-e2e-frontend,agent-e2e-app",
                "start:agent-tracer-gateway", "tracer",
            ], stages
        elif expected_status == 42:
            assert not any("agent-e2e-gateway" in call or "agent-tracer-gateway" in call for call in calls)
        else:
            assert not any("agent-tracer-gateway" in call or "agent-tracer" in call for call in calls)
        for suite in ("agent", "tracer"):
            expected_report = expected_status == 0 or (expected_status == 43 and suite == "agent")
            assert (artifacts / suite / "report.json").is_file() == expected_report
    for spec, suite in (("homepage", "generic"), ("agent-chat", "agent"), ("agent-tracer", "tracer")):
        artifacts = directory / f"single-{suite}"
        artifacts.mkdir()
        sentinel = artifacts / "previous-report.json"
        sentinel.write_text("{}")
        env = dict(os.environ, PATH=f"{directory}:{os.environ['PATH']}",
                   PHASE_LOG=str(directory / "phase.jsonl"), artifact_dir=str(artifacts), browser_spec=f"tests/e2e/{spec}.spec.js", AGENT_EXIT="0", BDD_EXIT="0")
        subprocess.run(["sh", "-c", script], env=env, check=True)
        assert (artifacts / suite / "report.json").is_file()
        assert not (artifacts / "report.json").exists()
        assert sentinel.is_file()
    # Sidebar has two sequential Playwright invocations as well.
    artifacts = directory / "sidebar-artifacts"
    env = dict(os.environ, PATH=f"{directory}:{os.environ['PATH']}",
               PHASE_LOG=str(directory / "phase.jsonl"), artifact_dir=str(artifacts), browser_spec="tests/e2e/agent-sidebar.spec.js", AGENT_EXIT="0", BDD_EXIT="0")
    subprocess.run(["sh", "-c", script], env=env, check=True)
    assert (artifacts / "sidebar/report.json").is_file()
    assert (artifacts / "sidebar-tracer/report.json").is_file()
print("Browser reports survive subsequent suites; BDD and agent failures stop subsequent stages")
