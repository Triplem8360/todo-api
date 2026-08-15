from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.core.config import Settings
from todo_api.core.security import hash_secret
from todo_api.exceptions.auth import (
    EmailNotVerifiedError,
    InvalidEmailVerificationTokenError,
)
from todo_api.models.user import User
from todo_api.schemas.user import UserCreateSchema
from todo_api.services.auth import AuthService

TEST_SECRET = "test-secret-key-with-at-least-thirty-two-bytes"


def settings() -> Settings:
    return Settings(_env_file=None, app_env="test", secret_key=TEST_SECRET)


def user(*, verified: bool, now: datetime | None = None) -> User:
    now = now or datetime.now(UTC)
    return User(
        id=7,
        email="user@example.com",
        full_name="Test User",
        hashed_password="password-hash",
        is_active=True,
        is_superuser=False,
        email_verified_at=now if verified else None,
        created_at=now,
        updated_at=now,
    )


def test_public_registration_stores_only_a_verification_token_hash() -> None:
    database_session = AsyncMock(spec=AsyncSession)
    registered_user = user(verified=False)
    payload = UserCreateSchema(
        email=registered_user.email,
        full_name=registered_user.full_name,
        password="password123",
    )
    service = AuthService(session=database_session, settings=settings())

    with (
        patch(
            "todo_api.services.auth.get_user_by_email",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "todo_api.services.auth.create_user",
            new=AsyncMock(return_value=registered_user),
        ) as create_user,
        patch(
            "todo_api.services.auth.to_thread.run_sync",
            new=AsyncMock(return_value="hashed-password"),
        ),
    ):
        pending = asyncio.run(service.register_pending_verification(payload))

    create_arguments = create_user.await_args.kwargs
    assert pending.user is registered_user
    assert pending.token != create_arguments["email_verification_token_hash"]
    assert hash_secret(pending.token) == create_arguments["email_verification_token_hash"]
    assert create_arguments["email_verified_at"] is None
    assert create_arguments["email_verification_expires_at"] == pending.expires_at
    database_session.commit.assert_awaited_once()


def test_email_verification_consumes_the_token_once() -> None:
    now = datetime.now(UTC)
    token = "verification-token-with-enough-entropy"
    pending_user = user(verified=False, now=now)
    pending_user.email_verification_token_hash = hash_secret(token)
    pending_user.email_verification_expires_at = now + timedelta(hours=1)
    pending_user.email_verification_requested_at = now
    database_session = AsyncMock(spec=AsyncSession)
    database_session.scalar.return_value = pending_user
    service = AuthService(session=database_session, settings=settings())

    verified_user = asyncio.run(service.verify_email(token))

    assert verified_user is pending_user
    assert pending_user.is_email_verified is True
    assert pending_user.email_verification_token_hash is None
    assert pending_user.email_verification_expires_at is None
    assert pending_user.email_verification_requested_at is None
    database_session.commit.assert_awaited_once()


def test_expired_email_verification_token_is_cleared_and_rejected() -> None:
    now = datetime.now(UTC)
    token = "expired-verification-token"
    pending_user = user(verified=False, now=now)
    pending_user.email_verification_token_hash = hash_secret(token)
    pending_user.email_verification_expires_at = now - timedelta(seconds=1)
    database_session = AsyncMock(spec=AsyncSession)
    database_session.scalar.return_value = pending_user
    service = AuthService(session=database_session, settings=settings())

    with pytest.raises(InvalidEmailVerificationTokenError):
        asyncio.run(service.verify_email(token))

    assert pending_user.email_verification_token_hash is None
    database_session.commit.assert_awaited_once()


def test_unverified_user_cannot_authenticate() -> None:
    database_session = AsyncMock(spec=AsyncSession)
    pending_user = user(verified=False)
    service = AuthService(session=database_session, settings=settings())

    with (
        patch(
            "todo_api.services.auth.get_user_by_email",
            new=AsyncMock(return_value=pending_user),
        ),
        patch(
            "todo_api.services.auth.to_thread.run_sync",
            new=AsyncMock(return_value=(True, None)),
        ),
        pytest.raises(EmailNotVerifiedError),
    ):
        asyncio.run(service.authenticate(pending_user.email, "password123"))


def test_resend_cooldown_does_not_rotate_or_send_another_token() -> None:
    now = datetime.now(UTC)
    pending_user = user(verified=False, now=now)
    pending_user.email_verification_requested_at = now
    pending_user.email_verification_token_hash = hash_secret("current-token")
    database_session = AsyncMock(spec=AsyncSession)
    database_session.scalar.return_value = pending_user
    service = AuthService(session=database_session, settings=settings())

    pending = asyncio.run(service.request_email_verification(pending_user.email))

    assert pending is None
    assert pending_user.email_verification_token_hash == hash_secret("current-token")
    database_session.commit.assert_not_awaited()
