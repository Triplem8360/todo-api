from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from todo_api.background.maintenance import (
    prune_oauth_authorization_codes,
    prune_refresh_sessions,
)
from todo_api.db.session import Database


def create_scheduler(database: Database) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(
        prune_oauth_authorization_codes,
        trigger="interval",
        minutes=5,
        kwargs={"database": database},
        id="prune-oauth-authorization-codes",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
    )

    scheduler.add_job(
        prune_refresh_sessions,
        trigger="interval",
        hours=1,
        kwargs={"database": database},
        id="prune-refresh-sessions",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
    )

    return scheduler
