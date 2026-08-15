from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

from fastapi import BackgroundTasks, Response
from fastapi_mail import MessageType

from todo_api.api.v1.routes.auth import confirm_email_verification, register
from todo_api.core.config import Settings
from todo_api.models.user import User
from todo_api.schemas.user import UserCreateSchema
from todo_api.services.auth import AuthService, PendingEmailVerification
from todo_api.services.email import EmailService

TEST_SECRET = "test-secret-key-with-at-least-thirty-two-bytes"


def test_registration_sends_a_multipart_verification_email() -> None:
    now = datetime.now(UTC)
    settings = Settings(_env_file=None, app_env="test", secret_key=TEST_SECRET)
    user = User(
        id=7,
        email="user@example.com",
        full_name="Test User",
        hashed_password="password-hash",
        is_active=True,
        is_superuser=False,
        email_verified_at=None,
        created_at=now,
        updated_at=now,
    )
    pending = PendingEmailVerification(
        user=user,
        token="opaque-verification-token",
        expires_at=now + timedelta(hours=24),
    )
    auth_service = Mock(spec=AuthService)
    auth_service.settings = settings
    auth_service.register_pending_verification = AsyncMock(return_value=pending)
    email_service = Mock(spec=EmailService)
    email_service.send = AsyncMock(return_value=True)
    payload = UserCreateSchema(
        email=user.email,
        full_name=user.full_name,
        password="password123",
    )

    result = asyncio.run(register(payload, auth_service, email_service, BackgroundTasks()))

    assert result.verification_email_sent is True
    assert result.is_email_verified is False
    send_arguments = email_service.send.await_args.kwargs
    assert send_arguments["recipient"] == user.email
    assert send_arguments["subtype"] is MessageType.html
    assert "opaque-verification-token" in send_arguments["body"]
    assert "opaque-verification-token" in send_arguments["alternative_body"]


def test_confirmation_sets_no_store_response_headers() -> None:
    now = datetime.now(UTC)
    verified_user = User(
        id=7,
        email="user@example.com",
        hashed_password="password-hash",
        is_active=True,
        is_superuser=False,
        email_verified_at=now,
    )
    auth_service = Mock(spec=AuthService)
    auth_service.verify_email = AsyncMock(return_value=verified_user)
    response = Response()

    result = asyncio.run(
        confirm_email_verification(
            response,
            auth_service,
            BackgroundTasks(),
            "opaque-verification-token",
        )
    )

    assert result.email_verified is True
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["referrer-policy"] == "no-referrer"
