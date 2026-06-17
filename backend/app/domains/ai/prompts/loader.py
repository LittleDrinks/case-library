"""Load and render runtime prompt bodies from product prompt assets."""

from __future__ import annotations

import json
from pathlib import Path
from string import Formatter

from .models import Prompt

PROMPTS_DIR = Path(__file__).resolve().parents[5] / "prompts"
RUNTIME_PROMPTS_DIR = PROMPTS_DIR / "runtime"
RUNTIME_PROMPTS_CONFIG = RUNTIME_PROMPTS_DIR / "prompts.json"


def load_runtime_prompt_body(asset_id: str, name: str) -> str:
    """Read one runtime prompt asset body."""
    asset_path = RUNTIME_PROMPTS_DIR / asset_id / f"{name}.md"
    return asset_path.read_text(encoding="utf-8").strip()


def _template_fields(template: str) -> set[str]:
    return {
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name
    }


def prompt_from_runtime_assets(
    *,
    id: str,
    asset_id: str,
    name: str,
    description: str,
    category: str,
    variables: tuple[str, ...],
    output_schema: str | None = None,
) -> Prompt:
    """Create a Prompt whose runtime bodies are loaded from prompts/runtime."""
    system_content = load_runtime_prompt_body(asset_id, "system")
    content = load_runtime_prompt_body(asset_id, "user")
    fields = _template_fields(content)
    missing = fields.difference(variables)
    if missing:
        raise ValueError(f"Runtime prompt {id} uses undeclared variables: {', '.join(sorted(missing))}")
    return Prompt(
        id=id,
        name=name,
        description=description,
        category=category,
        variables=variables,
        content=content,
        output_schema=output_schema,
        system_content=system_content,
    )


def load_runtime_prompts(config_path: Path = RUNTIME_PROMPTS_CONFIG) -> dict[str, Prompt]:
    """Load runtime prompt definitions from product-owned config and assets."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    prompts: dict[str, Prompt] = {}
    for item in config["prompts"]:
        prompt = prompt_from_runtime_assets(
            id=item["id"],
            asset_id=item["asset_id"],
            name=item["name"],
            description=item["description"],
            category=item["category"],
            variables=tuple(item["variables"]),
            output_schema=item.get("output_schema"),
        )
        prompts[prompt.id] = prompt
    return prompts


def render_prompt(prompt: Prompt, variables: dict) -> str:
    """Render a prompt body with the declared prompt variables only."""
    return prompt.content.format(**{name: variables[name] for name in prompt.variables})
