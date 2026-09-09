from __future__ import annotations

from dataclasses import dataclass, field

from pymongo.database import Database

from app.modules.agent.models import AgentArtifact, SourceRef


@dataclass(slots=True)
class ToolDeps:
    """单次 Run 内工具共享的服务端状态：真源读取与已检索来源。"""

    database: Database
    case_id: str
    thread_id: str
    run_id: str
    user: dict
    catalog: object
    catalog_state: object
    secret_path: str
    store: object = None
    version_id: str | None = None
    full_generation_allowed: bool = False
    sources: list[SourceRef] = field(default_factory=list)
    selected: list[dict] = field(default_factory=list)
    selections: list[dict] = field(default_factory=list)
    hits: list[SourceRef] = field(default_factory=list)
    evidence: list[SourceRef] = field(default_factory=list)
    proposed: AgentArtifact | None = None
    wrote: bool = False
