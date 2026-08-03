from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from todo_api.db.base import Base
from todo_api.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from todo_api.models.user import User


class RefreshSession(TimestampMixin, Base):
    """Server-side state for a rotating refresh token."""

    __tablename__ = "refresh_sessions"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="expiration"),
        CheckConstraint("absolute_expires_at > created_at", name="absolute_expiration"),
        CheckConstraint("expires_at <= absolute_expires_at", name="idle_before_absolute"),
        Index("ix_refresh_sessions_user_revoked", "user_id", "revoked_at"),
        Index("ix_refresh_sessions_expires_at", "expires_at"),
        Index("ix_refresh_sessions_absolute_expires_at", "absolute_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    previous_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="refresh_sessions", lazy="raise")

    def is_active(self, at: datetime | None = None) -> bool:
        now = at or datetime.now(UTC)
        return self.revoked_at is None and self.expires_at > now and self.absolute_expires_at > now

    def revoke(self, at: datetime | None = None) -> None:
        self.revoked_at = self.revoked_at or at or datetime.now(UTC)

    def rotate(self, token_hash: str, expires_at: datetime, at: datetime | None = None) -> None:
        rotated_at = at or datetime.now(UTC)

        if not self.is_active(rotated_at):
            raise ValueError("An inactive refresh session cannot be rotated.")

        self.previous_token_hash = self.token_hash
        self.token_hash = token_hash

        self.expires_at = self.expires_at = min(expires_at, self.absolute_expires_at)
        self.last_used_at = rotated_at
        self.rotated_at = rotated_at
