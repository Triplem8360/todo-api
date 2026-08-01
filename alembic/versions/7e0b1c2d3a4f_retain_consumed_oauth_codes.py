"""Retain consumed OAuth authorization codes.

Revision ID: 7e0b1c2d3a4f
Revises: e370ad374584
Create Date: 2026-08-01 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7e0b1c2d3a4f"
down_revision: str | Sequence[str] | None = "e370ad374584"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "oauth_authorization_codes",
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "oauth_authorization_codes",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "oauth_authorization_codes",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_oauth_authorization_codes_expiration"),
        "oauth_authorization_codes",
        "expires_at > created_at",
    )
    op.create_check_constraint(
        op.f("ck_oauth_authorization_codes_consumption_window"),
        "oauth_authorization_codes",
        "consumed_at IS NULL OR " "(consumed_at >= created_at AND consumed_at <= expires_at)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_oauth_authorization_codes_consumption_window"),
        "oauth_authorization_codes",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_oauth_authorization_codes_expiration"),
        "oauth_authorization_codes",
        type_="check",
    )
    op.drop_column("oauth_authorization_codes", "updated_at")
    op.drop_column("oauth_authorization_codes", "created_at")
    op.drop_column("oauth_authorization_codes", "consumed_at")
