from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

from fastapi_mail import MessageType

from todo_api.api.v1.routes.email import check_smtp_connection, send_test_email
from todo_api.models.user import User
from todo_api.schemas.email import EmailTestRequestSchema
from todo_api.services.email import EmailService


def active_user() -> User:
    return User(
        id=1,
        email="user@example.com",
        hashed_password="password-hash",
        is_active=True,
        is_superuser=False,
    )


def test_send_test_email_targets_only_the_authenticated_user() -> None:
    service = Mock(spec=EmailService)
    service.send = AsyncMock(return_value=True)
    user = active_user()
    payload = EmailTestRequestSchema(
        subject="SMTP endpoint test",
        body="The endpoint works.",
        subtype="html",
    )

    response = asyncio.run(send_test_email(payload, service, user))

    assert response.status == "sent"
    assert str(response.recipient) == user.email
    service.send.assert_awaited_once_with(
        recipient=user.email,
        subject=payload.subject,
        body=payload.body,
        subtype=MessageType.html,
    )


def test_smtp_connection_endpoint_returns_safe_configuration() -> None:
    service = Mock(spec=EmailService)
    service.check_connection = AsyncMock(return_value=True)
    service.config = Mock(
        MAIL_SERVER="smtp4dev",
        MAIL_PORT=25,
        MAIL_STARTTLS=False,
        MAIL_SSL_TLS=False,
        USE_CREDENTIALS=False,
        VALIDATE_CERTS=True,
    )

    response = asyncio.run(check_smtp_connection(service, active_user()))

    assert response.model_dump() == {
        "status": "ok",
        "server": "smtp4dev",
        "port": 25,
        "starttls": False,
        "ssl_tls": False,
        "use_credentials": False,
        "validate_certs": True,
    }
