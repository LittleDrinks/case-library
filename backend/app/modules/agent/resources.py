from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

RESOURCE_ROOT = Path(__file__).parent


@dataclass(frozen=True, slots=True)
class AgentResource:
    """Git 追踪的提示词或 Skill 资源：稳定标识、固定版本与内容哈希。"""

    kind: str
    id: str
    version: str
    relative_path: str

    def read(self) -> str:
        return (RESOURCE_ROOT / self.relative_path).read_text(encoding="utf-8")

    def content_hash(self) -> str:
        return hashlib.sha256(self.read().encode("utf-8")).hexdigest()

    def record(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "id": self.id,
            "version": self.version,
            "contentHash": self.content_hash(),
        }


SYSTEM_PROMPT = AgentResource("system-prompt", "agent/case-agent", "1", "prompts/case-agent.md")
TASK_PROMPT = AgentResource("task-prompt", "agent/revision-task", "1", "prompts/revision-task.md")
CASE_EDIT_SKILL = AgentResource(
    "skill", "case-edit-skill", "2.1", "skills/case-edit-skill/SKILL.md"
)


@lru_cache(maxsize=None)
def _cached_record(resource: AgentResource) -> dict[str, str]:
    return resource.record()


def resource_record(resource: AgentResource) -> dict[str, str]:
    return dict(_cached_record(resource))
