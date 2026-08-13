from __future__ import annotations

from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.connection import ConnectionPool, parse_url

from todo_api.background.maintenance import (
    prune_oauth_authorization_codes,
    prune_refresh_sessions,
)
from todo_api.core.config import Settings, get_settings
from todo_api.db.session import Database

_database: Database | None = None


def _get_database() -> Database:
    if _database is None:
        raise RuntimeError("The scheduler database is not available outside the app lifespan.")
    return _database


async def run_oauth_authorization_code_pruning() -> None:
    """Run OAuth code pruning with the database created by the app lifespan."""

    await prune_oauth_authorization_codes(_get_database())


async def run_refresh_session_pruning() -> None:
    """Run refresh-session pruning with the database created by the app lifespan."""

    await prune_refresh_sessions(_get_database())


def release_scheduler_database(database: Database) -> None:
    """Release the runtime database reference owned by a stopped scheduler."""

    global _database

    if _database is database:
        _database = None


def _create_redis_jobstore(settings: Settings) -> RedisJobStore:
    connect_args = parse_url(settings.redis_url)
    connect_args.update(
        db=settings.apscheduler_redis_db,
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
        health_check_interval=30,
        decode_responses=False,
    )
    connection_pool = ConnectionPool(**connect_args)

    return RedisJobStore(
        db=settings.apscheduler_redis_db,
        jobs_key=settings.apscheduler_jobs_key,
        run_times_key=settings.apscheduler_run_times_key,
        connection_pool=connection_pool,
    )


def create_scheduler(database: Database, settings: Settings | None = None) -> AsyncIOScheduler:
    global _database

    _database = database
    scheduler_settings = settings or get_settings()
    scheduler = AsyncIOScheduler(
        jobstores={"default": _create_redis_jobstore(scheduler_settings)},
        timezone="UTC",
    )

    scheduler.add_job(
        run_oauth_authorization_code_pruning,
        trigger="interval",
        minutes=5,
        id="prune-oauth-authorization-codes",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
    )

    scheduler.add_job(
        run_refresh_session_pruning,
        trigger="interval",
        seconds=10,
        id="prune-refresh-sessions",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
    )

    return scheduler
