from __future__ import annotations

from celery.signals import worker_process_init, worker_process_shutdown
from sqlalchemy.exc import SQLAlchemyError

from todo_api.background import maintenance
from todo_api.background.celery_app import celery_app
from todo_api.background.maintenance_runtime import (
    MaintenanceOperation,
    MaintenanceWorkerRuntime,
)
from todo_api.core.config import get_settings
from todo_api.db.session import Database, create_database

_MAINTENANCE_TASK_OPTIONS = {
    "autoretry_for": (SQLAlchemyError,),
    "retry_backoff": 5,
    "retry_jitter": True,
    "retry_kwargs": {"max_retries": 3},
}

_runtime = MaintenanceWorkerRuntime(lambda: create_database(get_settings()))


@worker_process_init.connect
def _initialize_maintenance_runtime(**_: object) -> None:
    _runtime.initialize()


@worker_process_shutdown.connect
def _shutdown_maintenance_runtime(**_: object) -> None:
    _runtime.shutdown()


def _run(operation: MaintenanceOperation) -> int:
    return _runtime.run(operation)


@celery_app.task(
    name="todo_api.maintenance.clear_expired_email_verification_tokens",
    **_MAINTENANCE_TASK_OPTIONS,
)
def clear_expired_email_verification_tokens() -> dict[str, int | str]:
    cleared = _run(maintenance.clear_expired_verification_tokens)
    return {"operation": "clear_expired_email_verification_tokens", "affected": cleared}


@celery_app.task(
    name="todo_api.maintenance.auto_archive_completed_todos",
    **_MAINTENANCE_TASK_OPTIONS,
)
def auto_archive_completed_todos() -> dict[str, int | str]:
    settings = get_settings()

    async def archive(database: Database) -> int:
        return await maintenance.auto_archive_completed_todos(
            database,
            after_days=settings.completed_todo_auto_archive_days,
        )

    archived = _run(archive)
    return {"operation": "auto_archive_completed_todos", "affected": archived}
