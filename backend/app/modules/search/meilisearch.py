from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Mapping

Kind = Literal["all", "case", "knowledge", "material"]
Role = Literal["anonymous", "user", "admin"]
MountField = Literal["workingCaseIds", "publishedVersionIds"]
KINDS = ("case", "knowledge", "material")
NEVER = 'catalogId = "__no_matching_document__"'
STOP_WORDS = re.compile(
    r"如何|怎么|怎样|请问|是否|可以|能够|通过|把|将|融入|结合|用于|有关|关于|相关|以及|进行|实现"
)
FACETS = {
    "all": ("tag", "publishedWithin"),
    "case": ("typeName", "audience", "tag", "publishedWithin"),
    "knowledge": (),
    "material": ("authority", "materialType", "tag", "publishedWithin", "accessLevel"),
}
FILTER_FIELDS = {
    "case": {"typeName": "typeName", "audience": "audience", "tag": "tags"},
    "knowledge": {},
    "material": {
        "authority": "authority",
        "materialType": "materialType",
        "tag": "tags",
        "accessLevel": "accessLevel",
    },
}
PERIOD_DAYS = {"7d": 7, "30d": 30, "365d": 365}
CASE_FIELDS = (
    "id",
    "kind",
    "title",
    "summary",
    "publishedAt",
    "typeId",
    "typeName",
    "course",
    "author",
    "organization",
    "stageText",
    "audience",
    "purpose",
    "likes",
)
KNOWLEDGE_FIELDS = (
    "id",
    "kind",
    "title",
    "summary",
    "edition",
    "chapterCount",
    "sectionCount",
    "sourceId",
    "chapterId",
    "chapter",
    "index",
    "unit",
)
MATERIAL_FIELDS = (
    "id",
    "kind",
    "title",
    "summary",
    "source",
    "sourceUrl",
    "tags",
    "publishedAt",
    "materialType",
    "authority",
    "accessLevel",
    "citedCount",
    "filename",
    "mediaType",
    "size",
    "hasFile",
)


class SearchUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str | None
    role: Role

    def __post_init__(self) -> None:
        if self.role not in {"anonymous", "user", "admin"}:
            raise ValueError("invalid principal role")
        authenticated = self.role in {"user", "admin"}
        if authenticated != bool(self.user_id):
            raise ValueError("authenticated principal requires a user id")


@dataclass(frozen=True, slots=True)
class MountedFilter:
    field: MountField
    value: str

    def __post_init__(self) -> None:
        valid_value = (
            isinstance(self.value, str) and 1 <= len(self.value.strip()) <= 100
        )
        if (
            self.field not in {"workingCaseIds", "publishedVersionIds"}
            or not valid_value
        ):
            raise ValueError("invalid mounted filter")


@dataclass(frozen=True, slots=True)
class CatalogKey:
    kind: Literal["case", "material"]
    id: str

    def __post_init__(self) -> None:
        if self.kind not in {"case", "material"} or not self.id.strip():
            raise ValueError("invalid catalog key")


@dataclass(frozen=True, slots=True)
class CatalogRequest:
    q: str
    kind: Kind
    generation: str
    index_uid: str
    index_epoch: str
    page_size: int
    offset: int
    filters: Mapping[str, object]
    principal: Principal
    mounted_filter: MountedFilter | None = None
    excluded_keys: tuple[CatalogKey, ...] = ()
    include_metadata: bool = True

    def __post_init__(self) -> None:
        allowed = {
            "typeName",
            "audience",
            "authority",
            "materialType",
            "tag",
            "publishedWithin",
            "accessLevel",
        }
        if self.kind not in {"all", *KINDS}:
            raise ValueError("invalid catalog kind")
        if (
            not self.generation.strip()
            or not self.index_uid.strip()
            or not self.index_epoch.strip()
        ):
            raise ValueError("catalog target is required")
        if not 1 <= self.page_size <= 100 or self.offset < 0:
            raise ValueError("invalid catalog pagination")
        if set(self.filters) - allowed:
            raise ValueError("invalid catalog filter")


@dataclass(frozen=True, slots=True)
class CatalogMetadata:
    total: int
    counts: dict[str, int]
    facets: dict[str, list[dict]]


@dataclass(frozen=True, slots=True)
class CatalogPage:
    items: list[dict]
    metadata: CatalogMetadata | None
    has_next: bool
    has_previous: bool


@dataclass(frozen=True, slots=True)
class _Plan:
    key: str
    payload: dict


def _quote(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _and(*clauses: str) -> str:
    active = [clause for clause in clauses if clause]
    return " AND ".join(active) if active else ""


def _or(*clauses: str) -> str:
    active = [clause for clause in clauses if clause]
    return (
        f"({' OR '.join(active)})" if len(active) > 1 else (active[0] if active else "")
    )


def _values(filters: Mapping[str, object], name: str) -> tuple[str, ...]:
    value = filters.get(name)
    if not value:
        return ()
    raw = value if isinstance(value, (list, tuple)) else (value,)
    return tuple(dict.fromkeys(str(item).strip() for item in raw if str(item).strip()))


def _in(field: str, values: tuple[str, ...]) -> str:
    encoded = ", ".join(_quote(value) for value in values)
    return f"{field} IN [{encoded}]"


def _excluded(request: CatalogRequest, kind: str) -> str:
    ids = tuple(key.id for key in request.excluded_keys if key.kind == kind)
    return f"id NOT IN [{', '.join(_quote(value) for value in ids)}]" if ids else ""


def _cutoff(period: str) -> str:
    return (datetime.now(UTC) - timedelta(days=PERIOD_DAYS[period])).date().isoformat()


def _filter_clause(field: str, name: str, values: tuple[str, ...]) -> str:
    if name == "publishedWithin":
        return f"publishedAt >= {_quote(_cutoff(values[0]))}"
    return _in(field, values)


def _business_clause(request: CatalogRequest, kind: str, skipped: str = "") -> str:
    clauses = []
    for name in request.filters:
        values = () if name == skipped else _values(request.filters, name)
        if not values:
            continue
        is_dated = name == "publishedWithin" and kind in {"case", "material"}
        field = "publishedAt" if is_dated else FILTER_FIELDS[kind].get(name)
        if not field:
            return NEVER
        clauses.append(_filter_clause(field, name, values))
    return _and(*clauses, _mount_clause(request, kind))


def _mount_clause(request: CatalogRequest, kind: str) -> str:
    mounted = request.mounted_filter
    if not mounted:
        return ""
    if kind != "material":
        return NEVER
    return f"{mounted.field} = {_quote(mounted.value)}"


def _allowed(principal: Principal) -> str:
    if principal.role == "admin":
        return ""
    if principal.role == "anonymous":
        return 'accessLevel = "public"'
    private = _and(
        'accessLevel = "private"', f"createdBy = {_quote(principal.user_id)}"
    )
    return _or('accessLevel IN ["public", "campus"]', private)


def _denied(principal: Principal) -> str:
    if principal.role == "admin":
        return NEVER
    if principal.role == "anonymous":
        return 'accessLevel IN ["campus", "private"]'
    return _and('accessLevel = "private"', f"createdBy != {_quote(principal.user_id)}")


def _case_access(principal: Principal) -> str:
    if principal.role == "anonymous":
        return 'docClass = "case-public"'
    if principal.role == "admin":
        return 'docClass = "case-private"'
    own = _and('docClass = "case-private"', f"createdBy = {_quote(principal.user_id)}")
    others = _and(
        'docClass = "case-campus"', f"createdBy != {_quote(principal.user_id)}"
    )
    return _or(own, others)


def _full_branch(request: CatalogRequest, kind: str, skipped: str = "") -> str:
    business = _business_clause(request, kind, skipped)
    if business == NEVER:
        return NEVER
    access = _allowed(request.principal) if kind == "material" else ""
    level = (
        _knowledge_level(request)
        if kind == "knowledge"
        else f"docClass = {_quote(kind)}"
    )
    if kind == "case":
        level = _case_access(request.principal)
    if kind == "material":
        level = 'docClass = "material-full"'
    return _and(
        f"kind = {_quote(kind)}", level, access, business, _excluded(request, kind)
    )


def _knowledge_level(request: CatalogRequest) -> str:
    level = "knowledge-section" if request.q.strip() else "knowledge-source"
    return f"docClass = {_quote(level)}"


def _restricted_business(request: CatalogRequest, skipped: str = "") -> str:
    compatible = {"accessLevel", "publishedWithin"}
    incompatible = set(request.filters) - compatible
    if any(_values(request.filters, name) for name in incompatible):
        return NEVER
    clauses = []
    for name in compatible:
        values = () if name == skipped else _values(request.filters, name)
        if values:
            field = "publishedAt" if name == "publishedWithin" else "accessLevel"
            clauses.append(_filter_clause(field, name, values))
    return _and(*clauses, _mount_clause(request, "material"))


def _restricted_branch(request: CatalogRequest, skipped: str = "") -> str:
    if request.kind not in {"all", "material"}:
        return NEVER
    business = _restricted_business(request, skipped)
    if business == NEVER:
        return NEVER
    return _and(
        'kind = "material"',
        _denied(request.principal),
        'docClass = "material-restricted"',
        "publicReferenceCount > 0",
        business,
        _excluded(request, "material"),
    )


def _full_scope(request: CatalogRequest, skipped: str = "") -> str:
    kinds = KINDS if request.kind == "all" else (request.kind,)
    branches = [_full_branch(request, kind, skipped) for kind in kinds]
    return _or(*(branch for branch in branches if branch != NEVER)) or NEVER


def _page_payload(request: CatalogRequest, index_uid: str) -> dict:
    restricted = _restricted_branch(request)
    branch = _full_scope(request)
    if restricted != NEVER:
        branch = _or(branch, restricted)
    payload = _payload(index_uid, request.q, branch, request.page_size + 1)
    payload["offset"] = request.offset
    payload["showRankingScore"] = True
    payload["sort"] = ["publishedAt:desc", "title:desc", "kind:desc", "id:desc"]
    return payload


def _payload(index_uid: str, query: str, filter_value: str, limit: int = 0) -> dict:
    return {
        "indexUid": index_uid,
        "q": query.strip(),
        "limit": limit,
        "filter": filter_value,
        "matchingStrategy": "frequency",
    }


def _count_plans(request: CatalogRequest, index_uid: str) -> list[_Plan]:
    knowledge = _knowledge_level(request)
    case = _and(
        'kind = "case"', _case_access(request.principal), _excluded(request, "case")
    )
    material = _and(
        'docClass = "material-full"',
        _allowed(request.principal),
        _excluded(request, "material"),
    )
    full_filter = _or(case, material, knowledge)
    full = _payload(index_uid, request.q, full_filter)
    full["facets"] = ["kind"]
    denied = _and(
        'docClass = "material-restricted"',
        _denied(request.principal),
        "publicReferenceCount > 0",
        _excluded(request, "material"),
    )
    restricted = _payload(index_uid, request.q, denied)
    restricted["attributesToSearchOn"] = ["title"]
    return [_Plan("count-full", full), _Plan("count-restricted", restricted)]


def _facet_payload(
    request: CatalogRequest,
    name: str,
    index_uid: str,
    period: str = "",
) -> dict:
    branch = _full_scope(request, name)
    if period:
        restricted = _restricted_branch(request, name)
        branch = _or(branch, restricted) if restricted != NEVER else branch
        branch = _and(branch, f"publishedAt >= {_quote(_cutoff(period))}")
    payload = _payload(index_uid, request.q, branch)
    if not period:
        payload["facets"] = ["tags" if name == "tag" else name]
    return payload


def _facet_plans(request: CatalogRequest, index_uid: str) -> list[_Plan]:
    plans = []
    for name in FACETS[request.kind]:
        periods = PERIOD_DAYS if name == "publishedWithin" else ("",)
        plans.extend(
            _Plan(
                f"facet-{name}-{period or 'full'}",
                _facet_payload(request, name, index_uid, period),
            )
            for period in periods
        )
    if "accessLevel" in FACETS[request.kind]:
        payload = _payload(
            index_uid, request.q, _restricted_branch(request, "accessLevel")
        )
        payload.update({"facets": ["accessLevel"], "attributesToSearchOn": ["title"]})
        plans.append(_Plan("facet-accessLevel-restricted", payload))
    return plans


def _page_plans(request: CatalogRequest, index_uid: str) -> list[_Plan]:
    return [_Plan("page", _page_payload(request, index_uid))]


def _metadata_plans(request: CatalogRequest, index_uid: str) -> list[_Plan]:
    return [*_count_plans(request, index_uid), *_facet_plans(request, index_uid)]


def _responses(raw: dict, plans: list[_Plan]) -> dict[str, dict]:
    results = raw.get("results") if isinstance(raw, dict) else None
    if not isinstance(results, list) or len(results) != len(plans):
        raise ValueError("invalid Meilisearch response")
    if not all(isinstance(result, dict) for result in results):
        raise ValueError("invalid Meilisearch result")
    return {plan.key: result for plan, result in zip(plans, results, strict=True)}


def _total(result: dict) -> int:
    value = result.get("estimatedTotalHits", result.get("totalHits", 0))
    return int(value)


def _restricted_hit(hit: dict) -> bool:
    return hit.get("docClass") == "material-restricted"


def _present_fields(hit: dict, fields: tuple[str, ...]) -> dict:
    return {field: hit[field] for field in fields if hit.get(field) is not None}


def _tokens(query: str) -> list[str]:
    chunks = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", query.lower())
    parts = [part for chunk in chunks for part in STOP_WORDS.split(chunk)]
    return list(dict.fromkeys(part for part in parts if len(part) >= 2))[:12]


def _score(hit: dict, query: str, restricted: bool = False) -> int:
    tokens = _tokens(query)
    if not tokens:
        return 1
    title, text = (
        str(hit.get("title", "")).lower(),
        str(hit.get("searchableText", "")).lower(),
    )
    return sum(
        12 if token in title else 4
        for token in tokens
        if restricted or token in title or token in text
    )


def _full_item(hit: dict, query: str) -> dict:
    kind = hit.get("kind")
    fields = {
        "case": CASE_FIELDS,
        "knowledge": KNOWLEDGE_FIELDS,
        "material": MATERIAL_FIELDS,
    }.get(kind, ("id", "kind", "title"))
    item = _present_fields(hit, fields)
    if kind == "case" and "theoryPoints" not in item:
        item["theoryPoints"] = list(hit.get("tags") or [])
    if kind == "material":
        item.update({"contentAvailable": True, "hasFile": bool(hit.get("hasFile"))})
    item["score"] = _score(hit, query)
    return item


def _restricted_item(hit: dict, query: str) -> dict:
    item = _present_fields(hit, ("id", "kind", "title", "accessLevel"))
    item.update(
        {
            "contentAvailable": False,
            "hasFile": bool(hit.get("hasFile")),
            "score": _score(hit, query, True),
        }
    )
    return item


def _items(request: CatalogRequest, page: dict) -> list[dict]:
    hits = page["hits"][: request.page_size]
    return [
        _restricted_item(hit, request.q)
        if _restricted_hit(hit)
        else _full_item(hit, request.q)
        for hit in hits
    ]


def _counts(responses: dict[str, dict]) -> dict[str, int]:
    raw = responses["count-full"].get("facetDistribution", {}).get("kind", {})
    counts = {kind: int(raw.get(kind, 0)) for kind in KINDS}
    counts["material"] += _total(responses["count-restricted"])
    return {"all": sum(counts.values()), **counts}


def _facet_rows(values: Mapping[str, int]) -> list[dict]:
    rows = ({"value": value, "count": int(count)} for value, count in values.items())
    return sorted(rows, key=lambda row: (-row["count"], row["value"]))


def _time_rows(responses: dict[str, dict]) -> list[dict]:
    return [
        {
            "value": period,
            "count": _total(
                responses[f"facet-publishedWithin-{period}"],
            ),
        }
        for period in PERIOD_DAYS
    ]


def _facet_values(responses: dict[str, dict], name: str) -> dict[str, int]:
    field = "tags" if name == "tag" else name
    values = dict(
        responses[f"facet-{name}-full"].get("facetDistribution", {}).get(field, {})
    )
    if name == "accessLevel":
        extra = (
            responses["facet-accessLevel-restricted"]
            .get("facetDistribution", {})
            .get(field, {})
        )
        for value, count in extra.items():
            values[value] = values.get(value, 0) + count
    return values


def _facets(request: CatalogRequest, responses: dict[str, dict]) -> dict:
    facets = {}
    for name in FACETS[request.kind]:
        facets[name] = (
            _time_rows(responses)
            if name == "publishedWithin"
            else _facet_rows(_facet_values(responses, name))
        )
    return facets


def _metadata(
    request: CatalogRequest, total: int, responses: dict[str, dict]
) -> CatalogMetadata | None:
    if not request.include_metadata:
        return None
    return CatalogMetadata(total, _counts(responses), _facets(request, responses))


def _catalog_page(
    request: CatalogRequest, page: dict, responses: dict[str, dict]
) -> CatalogPage:
    items, total = _items(request, page), _total(page)
    return CatalogPage(
        items,
        _metadata(request, total, responses),
        total > request.offset + len(items),
        request.offset > 0,
    )


class MeilisearchCatalog:
    def __init__(self, reader) -> None:
        self._reader = reader

    def health(
        self, index_uid: str, expected_generation: str, expected_epoch: str
    ) -> None:
        try:
            status = self._reader.health(index_uid)
            valid = status.generation == expected_generation
            valid = valid and status.index_epoch == expected_epoch
            if not status.available or status.primary_key != "catalogId" or not valid:
                raise ValueError("invalid stable catalog")
        except Exception as error:
            raise SearchUnavailable("检索暂不可用") from error

    def search(self, request: CatalogRequest) -> CatalogPage:
        try:
            plans = _page_plans(request, request.index_uid)
            if request.include_metadata:
                plans.extend(_metadata_plans(request, request.index_uid))
            queries = [plan.payload for plan in plans]
            snapshot = self._reader.search(request.index_uid, queries)
            if snapshot.index_epoch != request.index_epoch:
                raise SearchUnavailable("检索目录正在同步")
            responses = _responses(snapshot.response, plans)
            return _catalog_page(request, responses["page"], responses)
        except SearchUnavailable:
            raise
        except Exception as error:
            raise SearchUnavailable("检索暂不可用") from error
