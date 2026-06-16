#!/usr/bin/env python3
"""Local prompt rendering checks for runtime product prompts.

This harness intentionally does not call external AI services and does not
write runtime outputs. It validates the prompt loading/rendering boundary
against curated local fixtures.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from string import Formatter

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from prompt_registry.loader import load_runtime_prompts, render_prompt  # noqa: E402

DEFAULT_FIXTURE_PATH = REPO_ROOT / "product_prompts" / "runtime" / "evals" / "prompt_eval_cases.json"
INJECTION_MARKERS = (
    "忽略以上指令",
    "<<<END_USER_DATA>>>",
    "{system}",
    "secret-test-key",
)


def _load_cases(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{path} must contain a non-empty cases array")
    return cases


def _select_cases(cases: list[dict], prompt_ids: list[str]) -> list[dict]:
    if not prompt_ids:
        return cases
    selected = [case for case in cases if case.get("prompt_id") in set(prompt_ids)]
    missing = sorted(set(prompt_ids).difference({case.get("prompt_id") for case in selected}))
    if missing:
        raise ValueError(f"No fixture case found for prompt id(s): {', '.join(missing)}")
    return selected


def _assert_metadata_hides_bodies(prompt_id: str, metadata: dict) -> None:
    forbidden_keys = {"content", "system_content"}
    exposed = forbidden_keys.intersection(metadata)
    if exposed:
        raise AssertionError(f"{prompt_id} metadata exposes body field(s): {', '.join(sorted(exposed))}")


def _assert_required_variables(prompt_id: str, declared: tuple[str, ...], variables: dict) -> None:
    missing = [name for name in declared if name not in variables]
    if missing:
        raise AssertionError(f"{prompt_id} fixture is missing required variable(s): {', '.join(missing)}")


def _template_fields(template: str) -> set[str]:
    return {
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name
    }


def _assert_body_separation(prompt_id: str, system_content: str, rendered_user: str) -> None:
    if not system_content.strip():
        raise AssertionError(f"{prompt_id} has an empty system prompt")
    if system_content.strip() in rendered_user:
        raise AssertionError(f"{prompt_id} rendered user body contains the system prompt")
    leaked = [marker for marker in INJECTION_MARKERS if marker in system_content]
    if leaked:
        raise AssertionError(f"{prompt_id} system prompt contains fixture/user marker(s): {', '.join(leaked)}")


def _assert_rendered_values(prompt_id: str, template: str, variables: dict, rendered_user: str) -> None:
    referenced_fields = _template_fields(template)
    missing_values = [
        name
        for name, value in variables.items()
        if name in referenced_fields and isinstance(value, str) and value and value not in rendered_user
    ]
    if missing_values:
        raise AssertionError(
            f"{prompt_id} rendered user body is missing fixture value(s): {', '.join(missing_values)}"
        )


def run(fixture_path: Path, prompt_ids: list[str]) -> int:
    prompts = load_runtime_prompts()
    cases = _select_cases(_load_cases(fixture_path), prompt_ids)
    checked: list[str] = []

    for case in cases:
        prompt_id = case["prompt_id"]
        if prompt_id not in prompts:
            raise AssertionError(f"{prompt_id} exists in fixture but not runtime prompt config")

        prompt = prompts[prompt_id]
        variables = case.get("variables", {})
        if not isinstance(variables, dict):
            raise AssertionError(f"{prompt_id} fixture variables must be an object")

        _assert_metadata_hides_bodies(prompt_id, prompt.metadata())
        _assert_required_variables(prompt_id, prompt.variables, variables)
        rendered_user = render_prompt(prompt, variables)
        _assert_body_separation(prompt_id, prompt.system_content, rendered_user)
        _assert_rendered_values(prompt_id, prompt.content, variables, rendered_user)
        checked.append(prompt_id)

    print(f"prompt eval harness passed: {len(checked)} case(s) checked")
    for prompt_id in checked:
        print(f"- {prompt_id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Render and validate runtime prompt fixtures.")
    parser.add_argument("prompt_ids", nargs="*", help="Optional prompt id(s) to evaluate.")
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=DEFAULT_FIXTURE_PATH,
        help=f"Fixture JSON path. Default: {DEFAULT_FIXTURE_PATH}",
    )
    args = parser.parse_args()
    return run(args.fixtures, args.prompt_ids)


if __name__ == "__main__":
    raise SystemExit(main())
