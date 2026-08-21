from __future__ import annotations

from datetime import timedelta
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


def test_env_example_values_are_valid_settings() -> None:
    env_example = Path(__file__).parents[2] / ".env.example"

    settings = Settings(_env_file=env_example)

    assert settings.refresh_session_absolute_ttl == timedelta(days=90)
    assert settings.refresh_token_reuse_grace == timedelta(seconds=5)
    assert settings.email_verification_token_ttl == timedelta(hours=24)
    assert settings.email_verification_resend_cooldown == timedelta(seconds=60)


def test_redis_is_the_default_cache_backend() -> None:
    settings = Settings(_env_file=None, app_env="test", secret_key=TEST_SECRET)

    assert settings.cache_backend == "redis"
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.apscheduler_redis_db == 1
    assert settings.apscheduler_jobs_key == "todo-api:apscheduler:jobs"
    assert settings.apscheduler_run_times_key == "todo-api:apscheduler:run-times"
    assert settings.celery_broker_url == "redis://localhost:6379/2"
    assert settings.celery_result_backend == "redis://localhost:6379/3"
    assert settings.celery_result_expires_seconds == 3_600
    assert settings.celery_task_always_eager is False
    assert settings.completed_todo_auto_archive_days == 30


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


@pytest.mark.parametrize("field", ["celery_broker_url", "celery_result_backend"])
def test_celery_requires_redis_urls(field: str) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="test",
            secret_key=TEST_SECRET,
            **{field: "amqp://localhost:5672"},
        )


def test_mail_tls_modes_are_mutually_exclusive() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="test",
            secret_key=TEST_SECRET,
            mail_starttls=True,
            mail_ssl_tls=True,
        )


def test_mail_credentials_are_required_when_login_is_enabled() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="test",
            secret_key=TEST_SECRET,
            mail_use_credentials=True,
        )
