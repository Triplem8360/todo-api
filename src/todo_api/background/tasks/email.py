from __future__ import annotations

import asyncio

from fastapi_mail import MessageType

from todo_api.background.celery_app import celery_app
from todo_api.core.config import Settings, get_settings
from todo_api.exceptions.email import EmailServiceUnavailableError
from todo_api.services.email import EmailService
from todo_api.utils.email import (
    EmailContent,
    create_verification_email,
    create_welcome_email,
)

_EMAIL_TASK_OPTIONS = {
    "autoretry_for": (EmailServiceUnavailableError,),
    "retry_backoff": 2,
    "retry_jitter": True,
    "retry_kwargs": {"max_retries": 5},
}


async def _send_message(*, settings: Settings, recipient: str, message: EmailContent) -> bool:
    return await EmailService(settings).send(
        recipient=recipient,
        subject=message.subject,
        body=message.html_body,
        subtype=MessageType.html,
        alternative_body=message.plain_body,
    )


@celery_app.task(
    name="todo_api.email.send_registration_verification_email",
    **_EMAIL_TASK_OPTIONS,
)
def send_registration_verification_email(
    *,
    recipient: str,
    token: str,
    full_name: str | None,
) -> dict[str, bool | str]:
    """Deliver a registration verification email from a Celery worker."""

    settings = get_settings()
    message = create_verification_email(settings, token=token, full_name=full_name)
    delivered = asyncio.run(_send_message(settings=settings, recipient=recipient, message=message))
    return {"delivered": delivered, "email_type": "registration_verification"}


@celery_app.task(
    name="todo_api.email.send_registration_welcome_email",
    **_EMAIL_TASK_OPTIONS,
)
def send_registration_welcome_email(
    *,
    recipient: str,
    full_name: str | None,
) -> dict[str, bool | str]:
    """Welcome a user after their email address has been verified."""

    settings = get_settings()
    message = create_welcome_email(settings, full_name=full_name)
    delivered = asyncio.run(_send_message(settings=settings, recipient=recipient, message=message))
    return {"delivered": delivered, "email_type": "registration_welcome"}
