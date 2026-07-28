from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.core.config import Settings
from todo_api.core.security import (
    create_token_pair,
    decode_access_token,
    decode_refresh_token,
    hash_secret,
)
from todo_api.exceptions.auth import RefreshTokenReuseDetectedError
from todo_api.models.refresh_session import RefreshSession
from todo_api.models.user import User
from todo_api.services.auth import refresh_login_session


def test_refresh_token_rotates_the_session(settings: Settings) -> None:
    session_id = "b" * 64
    original = create_token_pair("7", session_id, settings)
    record = RefreshSession(
        id=session_id,
        user_id=7,
        token_hash=hash_secret(original.refresh_token),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    user = User(
        id=7,
        email="user@example.com",
        hashed_password="password-hash",
        is_active=True,
    )
    database_session = AsyncMock(spec=AsyncSession)
    database_session.scalar.return_value = record
    database_session.get.return_value = user

    rotated = asyncio.run(refresh_login_session(database_session, original.refresh_token, settings))

    access_payload = decode_access_token(rotated.access_token, settings)
    refresh_payload = decode_refresh_token(rotated.refresh_token, settings)
    assert access_payload.sub == refresh_payload.sub == "7"
    assert refresh_payload.session_id == session_id
    assert rotated.refresh_token != original.refresh_token
    assert record.token_hash == hash_secret(rotated.refresh_token)
    assert record.last_used_at is not None
    database_session.commit.assert_awaited_once()


def test_refresh_token_reuse_revokes_session(settings: Settings) -> None:
    session_id = "c" * 64
    token = create_token_pair("7", session_id, settings).refresh_token
    record = RefreshSession(
        id=session_id,
        user_id=7,
        token_hash=hash_secret("a newer refresh token"),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    database_session = AsyncMock(spec=AsyncSession)
    database_session.scalar.return_value = record

    with pytest.raises(RefreshTokenReuseDetectedError):
        asyncio.run(refresh_login_session(database_session, token, settings))

    assert record.revoked_at is not None
    database_session.commit.assert_awaited_once()
