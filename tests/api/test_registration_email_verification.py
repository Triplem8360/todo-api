from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

from fastapi import BackgroundTasks, Response
from starlette.requests import Request

from todo_api.api.v1.routes.auth import confirm_email_verification, register
from todo_api.core.config import Settings
from todo_api.models.user import User
from todo_api.schemas.user import UserCreateSchema
from todo_api.services.auth import AuthService, PendingEmailVerification

TEST_SECRET = "test-secret-key-with-at-least-thirty-two-bytes"
TEST_REQUEST_ID = "4bf92f35-24ce-4a23-b650-5a6d53dd51b8"


def request_with_context() -> Request:
    return Request({"type": "http", "state": {"request_id": TEST_REQUEST_ID}})


def test_registration_queues_a_verification_email() -> None:
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
    payload = UserCreateSchema(
        email=user.email,
        full_name=user.full_name,
        password="password123",
    )

    enqueue = AsyncMock(return_value=True)
    with patch(
        "todo_api.api.v1.routes.auth.enqueue_registration_verification_email",
        enqueue,
    ):
        result = asyncio.run(
            register(request_with_context(), payload, auth_service, BackgroundTasks())
        )

    assert result.verification_email_queued is True
    assert result.verification_email_sent is True
    enqueue.assert_awaited_once_with(
        user_id=user.id,
        recipient=user.email,
        token="opaque-verification-token",
        full_name=user.full_name,
        request_id=TEST_REQUEST_ID,
        expires_at=pending.expires_at,
    )


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

    enqueue = AsyncMock(return_value=True)
    with patch(
        "todo_api.api.v1.routes.auth.enqueue_registration_welcome_email",
        enqueue,
    ):
        result = asyncio.run(
            confirm_email_verification(
                request_with_context(),
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
    enqueue.assert_awaited_once_with(
        user_id=verified_user.id,
        recipient=verified_user.email,
        full_name=verified_user.full_name,
        request_id=TEST_REQUEST_ID,
    )
