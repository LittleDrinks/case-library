"""Product prompt definitions for server-side AI self-check workflows.

Prompt IDs are the stable contract used by `/api/prompts` and `/api/ai/chat`.
The registry exposes metadata only; prompt bodies stay server-side.
Long-form product prompt/template assets live under `prompts/`.
"""

from __future__ import annotations

from .loader import load_runtime_prompts
from .models import Prompt

PROMPTS: dict[str, Prompt] = load_runtime_prompts()


def get_prompt(prompt_id: str) -> Prompt | None:
    return PROMPTS.get(prompt_id)


def list_prompt_metadata(category: str | None = None) -> list[dict]:
    if not category:
        return []
    return [prompt.metadata() for prompt in PROMPTS.values() if prompt.category == category]
