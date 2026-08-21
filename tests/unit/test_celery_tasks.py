from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

from pytest import MonkeyPatch

from todo_api.background import dispatch
from todo_api.background.celery_app import create_celery_app
from todo_api.background.maintenance_runtime import MaintenanceWorkerRuntime
from todo_api.background.tasks import email as email_tasks
from todo_api.background.tasks import maintenance as maintenance_tasks
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
    assert app.conf.task_default_queue == "default"
    assert app.conf.task_routes == {
        "todo_api.email.*": {"queue": "emails"},
        "todo_api.maintenance.*": {"queue": "maintenance"},
    }
    assert (
        app.amqp.router.route({}, "todo_api.email.send_registration_verification_email")[
            "queue"
        ].name
        == "emails"
    )
    assert (
        app.amqp.router.route(
            {},
            "todo_api.maintenance.clear_expired_email_verification_tokens",
        )["queue"].name
        == "maintenance"
    )
    assert app.amqp.router.route({}, "todo_api.unrouted_task")["queue"].name == "default"
    assert app.conf.task_serializer == "json"
    assert app.conf.worker_prefetch_multiplier == 1


def test_celery_beat_schedules_real_maintenance_tasks_on_the_maintenance_queue() -> None:
    app = create_celery_app(task_settings())
    schedules = app.conf.beat_schedule

    assert set(schedules) == {
        "clear-expired-email-verification-tokens",
        "auto-archive-completed-todos",
    }
    assert {entry["task"] for entry in schedules.values()} == {
        "todo_api.maintenance.clear_expired_email_verification_tokens",
        "todo_api.maintenance.auto_archive_completed_todos",
    }
    assert all(entry["options"]["queue"] == "maintenance" for entry in schedules.values())
    assert all(entry["options"]["expires"] > 0 for entry in schedules.values())
    cleanup = schedules["clear-expired-email-verification-tokens"]
    assert cleanup["schedule"] == timedelta(seconds=30)
    assert cleanup["options"]["expires"] == 25


def test_maintenance_task_returns_an_observable_affected_count(
    monkeypatch: MonkeyPatch,
) -> None:
    run = Mock(return_value=7)
    monkeypatch.setattr(maintenance_tasks, "_run", run)

    result = maintenance_tasks.clear_expired_email_verification_tokens.run()

    assert result == {"operation": "clear_expired_email_verification_tokens", "affected": 7}
    run.assert_called_once_with(maintenance_tasks.maintenance.clear_expired_verification_tokens)


def test_maintenance_runtime_reuses_its_loop_and_database_until_shutdown() -> None:
    database = Mock()
    database.dispose = AsyncMock()
    database_factory = Mock(return_value=database)
    runtime = MaintenanceWorkerRuntime(database_factory)
    loops: list[asyncio.AbstractEventLoop] = []

    async def operation(actual_database: object) -> int:
        assert actual_database is database
        loops.append(asyncio.get_running_loop())
        return len(loops)

    try:
        assert runtime.run(operation) == 1
        assert runtime.run(operation) == 2
        assert loops[0] is loops[1]
        database_factory.assert_called_once_with()
        database.dispose.assert_not_awaited()
    finally:
        runtime.shutdown()

    database.dispose.assert_awaited_once_with()


def test_maintenance_worker_signals_manage_the_process_runtime(
    monkeypatch: MonkeyPatch,
) -> None:
    runtime = Mock()
    monkeypatch.setattr(maintenance_tasks, "_runtime", runtime)

    maintenance_tasks._initialize_maintenance_runtime()
    maintenance_tasks._shutdown_maintenance_runtime()

    runtime.initialize.assert_called_once_with()
    runtime.shutdown.assert_called_once_with()


def test_auto_archive_task_uses_the_configured_retention(monkeypatch: MonkeyPatch) -> None:
    settings = task_settings(completed_todo_auto_archive_days=45)
    database = Mock()
    archive = AsyncMock(return_value=3)
    monkeypatch.setattr(maintenance_tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(maintenance_tasks.maintenance, "auto_archive_completed_todos", archive)

    def run(operation: maintenance_tasks.MaintenanceOperation) -> int:
        return asyncio.run(operation(database))

    monkeypatch.setattr(maintenance_tasks, "_run", run)

    result = maintenance_tasks.auto_archive_completed_todos.run()

    assert result == {"operation": "auto_archive_completed_todos", "affected": 3}
    archive.assert_awaited_once_with(database, after_days=45)


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
