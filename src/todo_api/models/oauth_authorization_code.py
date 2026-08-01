from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from todo_api.db.base import Base
from todo_api.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from todo_api.models.user import User


class OAuthAuthorizationCode(TimestampMixin, Base):
    """Short-lived data bound to a one-time OAuth authorization code."""

    __tablename__ = "oauth_authorization_codes"
    __table_args__ = (
        CheckConstraint("char_length(code_hash) = 64", name="code_hash_length"),
        CheckConstraint("char_length(code_challenge) = 43", name="code_challenge_length"),
        CheckConstraint("char_length(client_id) > 0", name="client_id_not_empty"),
        CheckConstraint("char_length(redirect_uri) > 0", name="redirect_uri_not_empty"),
        CheckConstraint("expires_at > created_at", name="expiration"),
        CheckConstraint(
            "consumed_at IS NULL OR " 
            "(consumed_at >= created_at AND consumed_at <= expires_at)",
            name="consumption_window",
        ),
        Index("ix_oauth_authorization_codes_expires_at", "expires_at"),
    )

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[str] = mapped_column(String(128), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(43), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="oauth_authorization_codes", lazy="raise")
