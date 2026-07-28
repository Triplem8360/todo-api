from __future__ import annotations

import asyncio

from todo_api.core.config import get_settings
from todo_api.db.session import create_database


async def check_database() -> None:
    settings = get_settings()
    database = create_database(settings)
    try:
        await database.ping(settings.db_healthcheck_timeout_seconds)
        print("Database connection OK")
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(check_database())
