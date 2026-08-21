"""add Todo auto-archive index

Revision ID: c9a7d2e5f104
Revises: 8b2f4c6d7e8f
Create Date: 2026-08-20 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c9a7d2e5f104"
down_revision: str | Sequence[str] | None = "8b2f4c6d7e8f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_todos_status_archived_completed_at",
        "todos",
        ["status", "is_archived", "completed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_todos_status_archived_completed_at", table_name="todos")
