from __future__ import annotations

from celery import Celery

from todo_api.core.config import Settings, get_settings


def create_celery_app(settings: Settings | None = None) -> Celery:
    celery_settings = settings or get_settings()
    app = Celery(
        "todo_api",
        broker=celery_settings.celery_broker_url,
        backend=celery_settings.celery_result_backend,
        include=["todo_api.background.tasks.email"],
    )
    redis_transport_options = {
        "socket_connect_timeout": celery_settings.redis_connect_timeout_seconds,
        "socket_timeout": celery_settings.redis_socket_timeout_seconds,
    }
    app.conf.update(
        accept_content=["json"],
        broker_connection_retry_on_startup=True,
        broker_transport_options={
            **redis_transport_options,
            "visibility_timeout": 3_600,
        },
        enable_utc=True,
        result_backend_transport_options=redis_transport_options,
        result_expires=celery_settings.celery_result_expires_seconds,
        result_serializer="json",
        task_acks_late=True,
        task_always_eager=celery_settings.celery_task_always_eager,
        task_default_queue="emails",
        task_eager_propagates=True,
        task_reject_on_worker_lost=True,
        task_serializer="json",
        task_soft_time_limit=45,
        task_time_limit=60,
        timezone="UTC",
        worker_prefetch_multiplier=1,
    )
    return app


celery_app = create_celery_app()
