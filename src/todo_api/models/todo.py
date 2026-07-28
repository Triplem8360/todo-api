from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    false,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from todo_api.db.base import Base
from todo_api.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from todo_api.models.user import User


class TodoStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class TodoPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Todo(TimestampMixin, Base):
    __tablename__ = "todos"
    __table_args__ = (
        CheckConstraint("char_length(trim(title)) > 0", name="title_not_blank"),
        CheckConstraint(
            """
            (status = 'done' AND completed_at IS NOT NULL)
            OR
            (status <> 'done' AND completed_at IS NULL)
            """,
            name="completion_state",
        ),
        Index("ix_todos_user_status", "user_id", "status"),
        Index("ix_todos_user_due_at", "user_id", "due_at"),
        Index("ix_todos_user_archived", "user_id", "is_archived"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[TodoStatus] = mapped_column(
        SqlEnum(
            TodoStatus,
            name="todo_status",
            native_enum=False,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
            length=20,
        ),
        default=TodoStatus.TODO,
        server_default=TodoStatus.TODO.value,
        nullable=False,
    )

    priority: Mapped[TodoPriority] = mapped_column(
        SqlEnum(
            TodoPriority,
            name="todo_priority",
            native_enum=False,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
            length=10,
        ),
        default=TodoPriority.MEDIUM,
        server_default=TodoPriority.MEDIUM.value,
        nullable=False,
    )

    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="todos", lazy="raise")

    def complete(self, at: datetime | None = None) -> None:
        if self.status is TodoStatus.CANCELLED:
            raise ValueError("A cancelled todo cannot be completed.")

        self.status = TodoStatus.DONE
        self.completed_at = at or datetime.now(UTC)

    def reopen(self) -> None:
        self.status = TodoStatus.TODO
        self.completed_at = None

    def cancel(self) -> None:
        self.status = TodoStatus.CANCELLED
        self.completed_at = None

    def __repr__(self) -> str:
        return (
            f"Todo(id={self.id!r}, user_id={self.user_id!r}, "
            f"title={self.title!r}, status={self.status!r})"
        )
