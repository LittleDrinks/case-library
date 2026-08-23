from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

FilterValue = Annotated[str, Field(min_length=1, max_length=100)]


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
