"""Compatibility exports for product prompt registry."""

from __future__ import annotations

try:
    from .prompt_registry import PROMPTS, Prompt, get_prompt, list_prompt_metadata
except ImportError:
    from prompt_registry import PROMPTS, Prompt, get_prompt, list_prompt_metadata

__all__ = ["PROMPTS", "Prompt", "get_prompt", "list_prompt_metadata"]
