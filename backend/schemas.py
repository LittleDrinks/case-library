"""OpenAPI request and response schemas for the FastAPI app."""

from typing import Any

from pydantic import BaseModel, Field

JsonDict = dict[str, Any]


class SuccessMessageResponse(BaseModel):
    success: bool = True
    message: str


class LoginUser(BaseModel):
    id: int
    username: str
    role: str = Field(examples=["normal"])
    nickname: str = ""
    must_change_password: bool = False
    status: str = Field(default="active", examples=["active"])
    token: str = Field(description="HMAC-signed bearer token. This token is not a JWT.")


class LoginResponse(BaseModel):
    success: bool = True
    data: LoginUser


class PromptMetadata(BaseModel):
    id: str
    category: str
    name: str
    description: str = ""
    variables: list[str] = []
    output_schema: str | None = None


class PromptListResponse(BaseModel):
    success: bool = True
    data: list[PromptMetadata]


class AIChatRequest(BaseModel):
    prompt_id: str = Field(description="Prompt identifier returned by GET /api/prompts.")
    variables: JsonDict = Field(default_factory=dict)
    model: str | None = Field(default=None, description="Optional model name from AI_MODELS.")


class AIChatResponse(BaseModel):
    success: bool = True
    answer: str
    parsed: JsonDict | list[Any] | str | int | float | bool | None = None
    parse_error: str | None = None


class CaseData(BaseModel):
    id: int | None = None
    title: str | None = None
    type: str | None = None
    theme: str | None = None
    content: str | None = None
    source_material: str | None = None
    author: str | None = None
    owner_username: str | None = None
    department: str | None = None
    status: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    submitted_at: str | None = None
    review_at: str | None = None
    display_at: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    is_hidden: bool | None = None
    keywords: list[str] | None = None
    ai_reviews: list[JsonDict] | None = None

    model_config = {"extra": "allow"}


class CaseListResponse(BaseModel):
    success: bool = True
    data: list[CaseData]
    total: int


class CaseDetailResponse(BaseModel):
    success: bool = True
    data: CaseData


class CaseCreateResponse(BaseModel):
    success: bool = True
    message: str
    case_id: int | None = None
    case_ids: list[int] | None = None


class CaseDeletedStats(BaseModel):
    was_in_library: bool
    view_count: int
    like_count: int
    type: str | None = None
    theme: str | None = None


class CaseDeleteResponse(BaseModel):
    success: bool = True
    message: str
    deleted_stats: CaseDeletedStats


class CaseVisibilityResponse(BaseModel):
    success: bool = True
    message: str
    is_hidden: bool


class SearchResponse(BaseModel):
    success: bool = True
    data: list[CaseData]
    query: str | None = None


class ReviewData(BaseModel):
    id: int | None = None
    case_id: int | None = None
    version_id: int | None = None
    reviewer: str | None = None
    comment: str | None = None
    paragraph_comments: list[JsonDict] = Field(default_factory=list)
    status: str | None = None
    created_at: str | None = None
    review_at: str | None = None

    model_config = {"extra": "allow"}


class ReviewListResponse(BaseModel):
    success: bool = True
    data: list[ReviewData]


class VersionData(BaseModel):
    id: int | None = None
    case_id: int | None = None
    version_number: int | None = None
    title: str | None = None
    type: str | None = None
    theme: str | None = None
    content: str | None = None
    source_material: str | None = None
    author: str | None = None
    owner_username: str | None = None
    created_by: str | None = None
    paragraphs: list[JsonDict] = Field(default_factory=list)
    ai_review: JsonDict | None = None
    admin_comments: list[JsonDict] = Field(default_factory=list)
    change_reason: str | None = None
    created_at: str | None = None

    model_config = {"extra": "allow"}


class VersionListResponse(BaseModel):
    success: bool = True
    data: list[VersionData]


class StatisticsData(BaseModel):
    total_cases: int | None = None
    total_views: int | None = None
    total_likes: int | None = None
    by_type: dict[str, int] = Field(default_factory=dict)
    by_theme: dict[str, int] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class StatisticsResponse(BaseModel):
    success: bool = True
    data: StatisticsData


class ConstantsData(BaseModel):
    case_types: dict[str, str]
    themes: list[str]
    statuses: dict[str, str]


class ConstantsResponse(BaseModel):
    success: bool = True
    data: ConstantsData
