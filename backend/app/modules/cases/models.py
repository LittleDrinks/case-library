from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.cases.document_schema import (
    validate_optional_document,
    validate_prosemirror_document,
)
from app.modules.cases.template import new_case_document


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)

    title: str = Field(min_length=1, max_length=200)
    document: dict[str, Any] = Field(default_factory=new_case_document)

    validate_document = field_validator("document")(validate_prosemirror_document)


class CasePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    document: dict[str, Any] | None = None
    revision: int = Field(ge=1)

    validate_document = field_validator("document")(validate_optional_document)

    @model_validator(mode="after")
    def require_change(self) -> CasePatch:
        if self.title is None and self.document is None:
            raise ValueError("title 和 document 至少提供一项")
        return self


class LifecycleCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: Literal[
        "submit",
        "withdraw",
        "start",
        "approve",
        "reject",
        "supplement",
        "hide",
        "restore",
        "reopen",
        "snapshot",
        "rollback",
    ]
    revision: int = Field(ge=1)
    submittedVersionId: str | None = None
    targetId: str | None = None
    reasonType: str | None = Field(default=None, min_length=1, max_length=80)
    summary: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def require_review_reason(self) -> LifecycleCommand:
        if self.command in {"reject", "supplement"} and not self.reasonType:
            raise ValueError("退回或要求补充必须提供 reasonType")
        return self
