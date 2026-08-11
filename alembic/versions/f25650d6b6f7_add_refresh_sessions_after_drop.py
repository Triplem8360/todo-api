"""Add refresh sessions after drop

Revision ID: f25650d6b6f7
Revises: d0bf5b40031b
Create Date: 2026-07-27 15:29:26.131399

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f25650d6b6f7"
down_revision: Union[str, Sequence[str], None] = "d0bf5b40031b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    
    op.create_check_constraint(
        op.f("ck_refresh_sessions_absolute_expiration"),
        "refresh_sessions",
        "absolute_expires_at > created_at",
    )

    op.create_check_constraint(
        op.f("ck_refresh_sessions_idle_before_absolute"),
        "refresh_sessions",
        "expires_at <= absolute_expires_at",
    )


def downgrade() -> None:
    """Downgrade schema."""
    
    op.drop_constraint(
        op.f("ck_refresh_sessions_idle_before_absolute"),
        "refresh_sessions",
        type_="check",
    )

    op.drop_constraint(
        op.f("ck_refresh_sessions_absolute_expiration"),
        "refresh_sessions",
        type_="check",
    )
