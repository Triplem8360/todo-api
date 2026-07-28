"""drop redundant user email index

Revision ID: d72c03a55ac1
Revises: c1e9a65f3d20
Create Date: 2026-07-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d72c03a55ac1"
down_revision: str | Sequence[str] | None = "c1e9a65f3d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(op.f("ix_users_email"), table_name="users")


def downgrade() -> None:
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)
