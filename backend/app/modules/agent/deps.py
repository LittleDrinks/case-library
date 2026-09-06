from __future__ import annotations

from dataclasses import dataclass, field

from pymongo.database import Database

from app.modules.agent.models import SourceRef


@dataclass(slots=True)
class ToolDeps:
    """单次 Run 内工具共享的服务端状态。

    sources 是资料区保留来源（服务端真源，不随检索覆盖）；selected 是
    本条消息教师点选的来源；hits 是本次 Run 累计检索命中；evidence 是
    实际读过并固定版本的证据，供修订候选引用。
    """

    database: Database
    case_id: str
    thread_id: str
    run_id: str
    user: dict
    catalog: object
    catalog_state: object
    secret_path: str
    store: object = None
    write_enabled: bool = True
    case_version_id: str | None = None
    sources: list[SourceRef] = field(default_factory=list)
    selected: list[dict] = field(default_factory=list)
    selections: list[dict] = field(default_factory=list)
    hits: list[SourceRef] = field(default_factory=list)
    evidence: list[SourceRef] = field(default_factory=list)
    skills: tuple = ()
