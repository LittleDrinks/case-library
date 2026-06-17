"""Prompt data structures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    id: str
    name: str
    description: str
    category: str
    variables: tuple[str, ...]
    content: str
    output_schema: str | None = None
    system_content: str = ""

    def metadata(self) -> dict:
        """Return public prompt metadata without prompt body content."""
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "variables": list(self.variables),
        }
        if self.output_schema:
            data["output_schema"] = self.output_schema
        return data
