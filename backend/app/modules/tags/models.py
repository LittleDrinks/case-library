from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TagGroupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(min_length=1, max_length=80)
    required_for_submission: bool = Field(default=False, alias="requiredForSubmission")
    sort_key: int = Field(default=0, alias="sortKey")


class TagGroupPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=80)
    required_for_submission: bool | None = Field(
        default=None, alias="requiredForSubmission"
    )
    sort_key: int | None = Field(default=None, alias="sortKey")

    @model_validator(mode="after")
    def require_change(self) -> TagGroupPatch:
        fields = (self.name, self.required_for_submission, self.sort_key)
        if all(value is None for value in fields):
            raise ValueError("至少提供一项修改")
        return self


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(min_length=1, max_length=80)
    sort_key: int = Field(default=0, alias="sortKey")


class TagPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=80)
    group_id: str | None = Field(default=None, min_length=1, max_length=100)
    sort_key: int | None = Field(default=None, alias="sortKey")

    @model_validator(mode="after")
    def require_change(self) -> TagPatch:
        if self.name is None and self.group_id is None and self.sort_key is None:
            raise ValueError("至少提供一项修改")
        return self
