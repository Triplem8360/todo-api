"""Async producer boundary between FastAPI routes and Celery's synchronous publisher."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import cast

from celery.app.task import Task
from starlette.concurrency import run_in_threadpool

from todo_api.background.tasks.email import (
    send_registration_verification_email,
    send_registration_welcome_email,
)

logger = logging.getLogger(__name__)

_verification_email_task = cast(Task, send_registration_verification_email)
_welcome_email_task = cast(Task, send_registration_welcome_email)


async def _publish(
    task: Task,
    *,
    kwargs: dict[str, object],
    user_id: int,
    request_id: str,
    expires: datetime | None = None,
) -> bool:
    try:
        result = await run_in_threadpool(
            task.apply_async,
            kwargs=kwargs,
            kwargsrepr=repr(dict.fromkeys(kwargs, "<redacted>")),
            headers={"request_id": request_id},
            expires=expires,
            retry=False,
        )
    except Exception:
        logger.exception(
            "Celery task publish failed",
            extra={"task_name": task.name, "user_id": user_id},
        )
        return False

    logger.info(
        "Celery task queued",
        extra={"task_id": result.id, "task_name": task.name, "user_id": user_id},
    )
    return True


async def enqueue_registration_verification_email(
    *,
    user_id: int,
    recipient: str,
    token: str,
    full_name: str | None,
    request_id: str,
    expires_at: datetime,
) -> bool:
    return await _publish(
        _verification_email_task,
        kwargs={"recipient": recipient, "token": token, "full_name": full_name},
        user_id=user_id,
        request_id=request_id,
        expires=expires_at,
    )


async def enqueue_registration_welcome_email(
    *,
    user_id: int,
    recipient: str,
    full_name: str | None,
    request_id: str,
) -> bool:
    return await _publish(
        _welcome_email_task,
        kwargs={"recipient": recipient, "full_name": full_name},
        user_id=user_id,
        request_id=request_id,
    )
