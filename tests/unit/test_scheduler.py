from __future__ import annotations

from typing import cast

from apscheduler.jobstores.redis import RedisJobStore
from redis.connection import SSLConnection

from todo_api.background.scheduler import create_scheduler, release_scheduler_database
from todo_api.core.config import Settings
from todo_api.db.session import Database

TEST_SECRET = "test-secret-key-with-at-least-thirty-two-bytes"


def test_scheduler_uses_redis_db_one_without_serializing_database() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        secret_key=TEST_SECRET,
        redis_url="rediss://redis-user:redis-password@redis.example:6380/0",
    )
    database = cast(Database, object())

    scheduler = create_scheduler(database, settings)

    try:
        jobstore = scheduler._jobstores["default"]
        assert isinstance(jobstore, RedisJobStore)
        assert jobstore.jobs_key == settings.apscheduler_jobs_key
        assert jobstore.run_times_key == settings.apscheduler_run_times_key

        connection = jobstore.redis.connection_pool.connection_kwargs
        assert connection["db"] == 1
        assert connection["host"] == "redis.example"
        assert connection["port"] == 6380
        assert connection["username"] == "redis-user"
        assert connection["password"] == "redis-password"
        assert jobstore.redis.connection_pool.connection_class is SSLConnection

        jobs = {job.id: job for job in scheduler.get_jobs()}
        assert jobs["prune-oauth-authorization-codes"].kwargs == {}
        assert jobs["prune-refresh-sessions"].kwargs == {}
    finally:
        release_scheduler_database(database)
