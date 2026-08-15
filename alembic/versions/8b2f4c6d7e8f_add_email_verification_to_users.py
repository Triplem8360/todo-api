"""add email verification to users

Revision ID: 8b2f4c6d7e8f
Revises: 7e0b1c2d3a4f
Create Date: 2026-08-14 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8b2f4c6d7e8f"
down_revision: str | Sequence[str] | None = "7e0b1c2d3a4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("email_verification_token_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("email_verification_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("email_verification_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_users_email_verification_token_hash",
        "users",
        ["email_verification_token_hash"],
    )

    # Accounts created before verification existed must remain usable.
    op.execute(
        sa.text(
            "UPDATE users "
            "SET email_verified_at = COALESCE(created_at, CURRENT_TIMESTAMP) "
            "WHERE email_verified_at IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_users_email_verification_token_hash",
        "users",
        type_="unique",
    )
    op.drop_column("users", "email_verification_requested_at")
    op.drop_column("users", "email_verification_expires_at")
    op.drop_column("users", "email_verification_token_hash")
    op.drop_column("users", "email_verified_at")
