from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from todo_api.core.config import Settings

TEST_SECRET = "test-secret-key-with-at-least-thirty-two-bytes"


def test_env_example_matches_settings_validation_aliases() -> None:
    env_example = Path(__file__).parents[2] / ".env.example"
    env_keys = {
        line.partition("=")[0]
        for line in env_example.read_text().splitlines()
        if line and not line.startswith("#")
    }
    validation_aliases = {str(field.validation_alias) for field in Settings.model_fields.values()}

    assert env_keys == validation_aliases


def test_redis_is_the_default_cache_backend() -> None:
    settings = Settings(_env_file=None, app_env="test", secret_key=TEST_SECRET)

    assert settings.cache_backend == "redis"
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.apscheduler_redis_db == 1
    assert settings.apscheduler_jobs_key == "todo-api:apscheduler:jobs"
    assert settings.apscheduler_run_times_key == "todo-api:apscheduler:run-times"


@pytest.mark.parametrize(
    "redis_url",
    [
        "http://localhost:6379/0",
        "redis:///0",
        "redis://localhost:6379/0#fragment",
    ],
)
def test_redis_url_requires_a_supported_absolute_url(redis_url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="test",
            secret_key=TEST_SECRET,
            redis_url=redis_url,
        )
