from __future__ import annotations

import asyncio
from typing import Any

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from todo_api.core.config import get_settings
from todo_api.db.base import Base

# Register ORM models in Base.metadata.
import todo_api.models  # noqa: F401

config = context.config
target_metadata = Base.metadata


def get_database_url() -> str:
    return get_settings().database_url


def get_context_options() -> dict[str, Any]:
    database_url = get_database_url()

    return {
        "target_metadata": target_metadata,
        "compare_type": True,
        "compare_server_default": True,
        "render_as_batch": database_url.startswith("sqlite"),
    }


def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""

    context.configure(
        url=get_database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **get_context_options(),
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run Alembic's synchronous migration API on a sync connection."""

    context.configure(
        connection=connection,
        **get_context_options(),
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and execute Alembic migrations."""

    engine = create_async_engine(
        get_database_url(),
        poolclass=pool.NullPool,
    )

    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    """Run migrations using the async database driver."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
