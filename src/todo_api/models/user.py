from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from todo_api.db.base import Base
from todo_api.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from todo_api.models.api_key import APIKey
    from todo_api.models.oauth_authorization_code import OAuthAuthorizationCode
    from todo_api.models.refresh_session import RefreshSession
    from todo_api.models.todo import Todo


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    full_name: Mapped[str | None] = mapped_column(String(150), default=None)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    email_verification_token_hash: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        nullable=True,
    )
    email_verification_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    email_verification_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    api_keys: Mapped[list[APIKey]] = relationship(
        "APIKey",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )

    refresh_sessions: Mapped[list[RefreshSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )

    todos: Mapped[list[Todo]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )

    oauth_authorization_codes: Mapped[list[OAuthAuthorizationCode]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, email={self.email!r})"
