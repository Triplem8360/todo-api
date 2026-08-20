from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

from pytest import MonkeyPatch

from todo_api.background import dispatch
from todo_api.background.celery_app import create_celery_app
from todo_api.background.tasks import email as email_tasks
from todo_api.core.config import Settings

TEST_SECRET = "test-secret-key-with-at-least-thirty-two-bytes"
TEST_REQUEST_ID = "4bf92f35-24ce-4a23-b650-5a6d53dd51b8"
TEST_EXPIRES_AT = datetime(2026, 8, 21, tzinfo=UTC)


def task_settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        secret_key=TEST_SECRET,
        mail_suppress_send=True,
        **overrides,
    )


def test_celery_uses_separate_redis_broker_and_result_databases() -> None:
    settings = task_settings(
        celery_broker_url="redis://broker.example.com:6379/2",
        celery_result_backend="redis://results.example.com:6379/3",
        celery_result_expires_seconds=900,
    )

    app = create_celery_app(settings)

    assert app.conf.broker_url == settings.celery_broker_url
    assert app.conf.result_backend == settings.celery_result_backend
    assert app.conf.result_expires == 900
    assert app.conf.task_default_queue == "emails"
    assert app.conf.task_serializer == "json"
    assert app.conf.worker_prefetch_multiplier == 1


def test_verification_task_builds_and_sends_a_multipart_email(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(email_tasks, "get_settings", lambda: task_settings())
    send_message = AsyncMock(return_value=True)
    monkeypatch.setattr(email_tasks, "_send_message", send_message)

    result = email_tasks.send_registration_verification_email.run(
        recipient="user@example.com",
        token="opaque-verification-token",
        full_name="Test User",
    )

    assert result == {"delivered": True, "email_type": "registration_verification"}
    arguments = send_message.await_args.kwargs
    assert arguments["recipient"] == "user@example.com"
    assert "opaque-verification-token" in arguments["message"].html_body
    assert "opaque-verification-token" in arguments["message"].plain_body


def test_welcome_task_runs_after_email_verification(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(email_tasks, "get_settings", lambda: task_settings())
    send_message = AsyncMock(return_value=True)
    monkeypatch.setattr(email_tasks, "_send_message", send_message)

    result = email_tasks.send_registration_welcome_email.run(
        recipient="user@example.com",
        full_name="Test User",
    )

    assert result == {"delivered": True, "email_type": "registration_welcome"}
    assert send_message.await_args.kwargs["message"].subject == "Welcome to Todo API"


def test_dispatch_reports_a_successful_publish_without_logging_payloads(
    monkeypatch: MonkeyPatch,
) -> None:
    run_in_threadpool = AsyncMock(return_value=Mock(id="task-123"))
    monkeypatch.setattr(dispatch, "run_in_threadpool", run_in_threadpool)

    queued = asyncio.run(
        dispatch.enqueue_registration_verification_email(
            user_id=7,
            recipient="user@example.com",
            token="secret-token",
            full_name="Test User",
            request_id=TEST_REQUEST_ID,
            expires_at=TEST_EXPIRES_AT,
        )
    )

    assert queued is True
    publish_options = run_in_threadpool.await_args.kwargs
    assert publish_options["retry"] is False
    assert publish_options["expires"] == TEST_EXPIRES_AT
    assert publish_options["headers"] == {"request_id": TEST_REQUEST_ID}
    assert "secret-token" not in publish_options["kwargsrepr"]
    assert publish_options["kwargs"]["token"] == "secret-token"


def test_dispatch_returns_false_when_redis_is_unavailable(monkeypatch: MonkeyPatch) -> None:
    run_in_threadpool = AsyncMock(side_effect=OSError("redis unavailable"))
    monkeypatch.setattr(dispatch, "run_in_threadpool", run_in_threadpool)

    queued = asyncio.run(
        dispatch.enqueue_registration_welcome_email(
            user_id=7,
            recipient="user@example.com",
            full_name="Test User",
            request_id=TEST_REQUEST_ID,
        )
    )

    assert queued is False
