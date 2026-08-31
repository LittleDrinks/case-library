from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent


agent = Agent(
    output_type=str,
    name="case-library-agent",
    defer_model_check=True,
)
_PROMPT_DIR = Path(__file__).parent / "prompts"


def prompt_text(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8").strip()


def _node_text(node: object) -> str:
    if not isinstance(node, dict):
        return ""
    if isinstance(node.get("text"), str):
        return node["text"]
    return "".join(_node_text(child) for child in node.get("content", []))


def case_instructions(case: dict) -> str:
    title = str(case.get("title") or "未命名案例")
    text = _node_text(case.get("document"))[:12000]
    return "\n\n".join(
        (
            prompt_text("case-agent.md"),
            f"当前案例标题：{title}",
            f"当前案例正文：{text}",
        )
    )
