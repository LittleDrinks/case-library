from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

FilterValue = Annotated[str, Field(min_length=1, max_length=100)]


class TagLeaf(BaseModel):
    """标签条件叶子：引用目录中的原生标签 ID。"""

    model_config = ConfigDict(extra="forbid")

    tagId: FilterValue


class TagExpression(BaseModel):
    """嵌套混合条件：op 为 and/or，children 为叶子或嵌套表达式。"""

    model_config = ConfigDict(extra="forbid")

    op: Literal["and", "or"]
    children: list[Union["TagExpression", TagLeaf]] = Field(
        min_length=1, max_length=32
    )


TagExpression.model_rebuild()


def flat_tag_condition(tag_ids: list[str], tag_mode: str) -> TagExpression | None:
    """把页面式 tagIds+tagMode 糖规范化为混合条件；空集合表示无条件。"""
    if not tag_ids:
        return None
    children = [TagLeaf(tagId=value) for value in dict.fromkeys(tag_ids)]
    op = "and" if tag_mode == "all" else "or"
    return TagExpression(op=op, children=children)


class SearchQuery(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    q: str = Field(default="", max_length=200)
    kind: Literal["all", "case", "knowledge", "material"] = "all"
    cursor: str | None = Field(default=None, min_length=1, max_length=2_000)
    page_size: int = Field(default=20, ge=1, le=100, alias="pageSize")
    type_name: list[FilterValue] = Field(
        default_factory=list, max_length=20, alias="typeName"
    )
    audience: list[FilterValue] = Field(default_factory=list, max_length=20)
    authority: list[FilterValue] = Field(default_factory=list, max_length=20)
    material_type: list[FilterValue] = Field(
        default_factory=list,
        max_length=20,
        alias="materialType",
    )
    tag: list[FilterValue] = Field(default_factory=list, max_length=20)
    published_within: Literal["7d", "30d", "365d"] | None = Field(
        default=None,
        alias="publishedWithin",
    )
    access_level: Literal["public"] | None = Field(default=None, alias="accessLevel")
    mounted_case_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        alias="mountedInCaseId",
    )
    tag_mode: Literal["all", "any"] = Field(default="all", alias="tagMode")
    tag_ids: list[FilterValue] = Field(
        default_factory=list,
        max_length=20,
        alias="tagIds",
    )

    def condition(self) -> TagExpression | None:
        return flat_tag_condition(self.tag_ids, self.tag_mode)

    def filters(self) -> dict:
        return {
            "typeName": self.type_name,
            "audience": self.audience,
            "authority": self.authority,
            "materialType": self.material_type,
            "tag": self.tag,
            "publishedWithin": self.published_within,
            "accessLevel": [self.access_level] if self.access_level else [],
            "mountedInCaseId": self.mounted_case_id,
        }


class SearchRequest(SearchQuery):
    """POST /api/search 请求体：在页面条件之外接受嵌套混合标签条件。"""

    tag_expression: TagExpression | None = Field(default=None, alias="tagExpression")

    @model_validator(mode="after")
    def exclusive_condition(self) -> SearchRequest:
        if self.tag_expression is not None and (self.tag_ids or self.tag_mode != "all"):
            raise ValueError("tagExpression 不能与 tagIds 或非默认 tagMode 同时使用")
        return self

    def condition(self) -> TagExpression | None:
        return self.tag_expression or flat_tag_condition(self.tag_ids, self.tag_mode)


class SearchItem(BaseModel):
    """结果条目：公共字段必填，类型专属字段按 kind 可选。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["case", "knowledge", "material"]
    title: str
    score: int
    summary: str | None = None
    publishedAt: str | None = None
    typeId: str | None = None
    typeName: str | None = None
    course: str | None = None
    author: str | None = None
    organization: str | None = None
    stageText: str | None = None
    audience: str | None = None
    purpose: str | None = None
    likes: int | None = None
    tagIds: list[str] | None = None
    edition: str | None = None
    chapterCount: int | None = None
    sectionCount: int | None = None
    sourceId: str | None = None
    chapterId: str | None = None
    chapter: str | None = None
    index: int | None = None
    unit: str | None = None
    source: str | None = None
    sourceUrl: str | None = None
    tags: list[str] | None = None
    materialType: str | None = None
    authority: str | None = None
    accessLevel: str | None = None
    citedCount: int | None = None
    filename: str | None = None
    mediaType: str | None = None
    size: int | None = None
    hasFile: bool | None = None
    contentAvailable: bool | None = None


class FacetRow(BaseModel):
    """分面计数字：value 为维度取值，count 为当前可见结果数。"""

    value: str
    count: int


class CountSummary(BaseModel):
    """分类计数：与结果页同条件，含受限资料引用计数。"""

    all: int
    case: int
    knowledge: int
    material: int


class SearchResponse(BaseModel):
    """GET/POST /api/search 统一响应：结构对齐现有前端契约。"""

    model_config = ConfigDict(extra="forbid")

    query: str
    kind: Literal["all", "case", "knowledge", "material"]
    tagCondition: TagExpression | None = None
    page: int
    pageSize: int
    items: list[SearchItem]
    total: int | None = None
    counts: CountSummary | None = None
    facets: dict[str, list[FacetRow]] | None = None
    metadataIncluded: bool
    nextCursor: str | None = None
    previousCursor: str | None = None


class SearchSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(max_length=200)
    items: list[dict[str, object]] = Field(max_length=15)
