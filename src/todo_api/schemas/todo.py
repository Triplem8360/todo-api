from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from todo_api.models.todo import TodoPriority, TodoStatus


class TodoSortField(StrEnum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    DUE_AT = "due_at"
    TITLE = "title"


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


def _normalize_title(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Title must not be blank.")
    return normalized


def _normalize_description(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _require_timezone(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("Datetime values must include a timezone offset.")
    return value


class TodoCreateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5_000)
    priority: TodoPriority = TodoPriority.MEDIUM
    due_at: AwareDatetime | None = Field(default=None, examples=["2026-07-28T14:30:00Z"])

    _validate_title = field_validator("title")(_normalize_title)
    _validate_description = field_validator("description")(_normalize_description)


class TodoUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5_000)
    status: TodoStatus | None = None
    priority: TodoPriority | None = None
    due_at: AwareDatetime | None = None
    is_archived: bool | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Title cannot be null.")
        return _normalize_title(value)

    _validate_description = field_validator("description")(_normalize_description)

    @field_validator("status", "priority", "is_archived")
    @classmethod
    def reject_null_non_nullable_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null.")
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        return self


class TodoListQuerySchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(default=None, min_length=1, max_length=100)
    status: TodoStatus | None = None
    priority: TodoPriority | None = None
    is_archived: bool = False

    due_from: AwareDatetime | None = None
    due_to: AwareDatetime | None = None

    sort_by: TodoSortField = TodoSortField.CREATED_AT
    sort_direction: SortDirection = SortDirection.DESC

    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("q")
    @classmethod
    def normalize_search(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Search text must not be blank.")
        return normalized

    @model_validator(mode="after")
    def validate_due_range(self) -> Self:
        if self.due_from and self.due_to and self.due_from > self.due_to:
            raise ValueError("due_from must be earlier than or equal to due_to.")
        return self


class TodoResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: TodoStatus
    priority: TodoPriority
    due_at: datetime | None
    completed_at: datetime | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class TodoListResponseSchema(BaseModel):
    items: list[TodoResponseSchema]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
