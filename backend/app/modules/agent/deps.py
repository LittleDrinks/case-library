from __future__ import annotations

from dataclasses import dataclass, field

from pymongo.database import Database

from app.modules.agent.models import SourceRef


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
    sources: list[SourceRef] = field(default_factory=list)
