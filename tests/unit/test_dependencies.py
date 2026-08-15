from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.security import HTTPBasicCredentials
from pwdlib.exceptions import UnknownHashError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.api.deps import (
    get_current_basic_user,
    get_current_header_api_key_user,
    get_current_query_api_key_user,
)
from todo_api.core.security import generate_api_key, hash_secret
from todo_api.exceptions.api_key import APIKeyRequiredError
from todo_api.exceptions.auth import (
    BasicAuthenticationUnavailableError,
    InvalidBasicCredentialsError,
)
from todo_api.models.api_key import APIKey
from todo_api.models.user import User

APIKeyDependency = Callable[[str | None, AsyncSession], Awaitable[User]]


def active_user() -> User:
    return User(
        id=1,
        email="user@example.com",
        hashed_password="password-hash",
        is_active=True,
        is_superuser=False,
        email_verified_at=datetime.now(UTC),
    )


def test_basic_authentication() -> None:
    user = active_user()
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = user
    credentials = HTTPBasicCredentials(
        username=user.email,
        password="strong-pass-123",
    )

    with patch(
        "todo_api.api.deps.to_thread.run_sync",
        new=AsyncMock(return_value=True),
    ):
        authenticated = asyncio.run(get_current_basic_user(credentials, session))

    assert authenticated is user


def test_missing_basic_credentials_skip_database_and_hashing() -> None:
    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(InvalidBasicCredentialsError):
        asyncio.run(get_current_basic_user(None, session))

    session.scalar.assert_not_awaited()


def test_basic_authentication_maps_database_failure() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = SQLAlchemyError("database unavailable")
    credentials = HTTPBasicCredentials(username="user@example.com", password="password")

    with pytest.raises(BasicAuthenticationUnavailableError):
        asyncio.run(get_current_basic_user(credentials, session))


def test_basic_authentication_maps_unknown_password_hash() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = active_user()
    credentials = HTTPBasicCredentials(username="user@example.com", password="password")

    with (
        patch(
            "todo_api.api.deps.to_thread.run_sync",
            new=AsyncMock(side_effect=UnknownHashError("invalid-hash")),
        ),
        pytest.raises(BasicAuthenticationUnavailableError),
    ):
        asyncio.run(get_current_basic_user(credentials, session))


@pytest.mark.parametrize(
    "dependency",
    [get_current_header_api_key_user, get_current_query_api_key_user],
)
def test_api_key_transports_share_validation(dependency: APIKeyDependency) -> None:
    user = active_user()
    raw_key = generate_api_key()
    record = APIKey(
        id=1,
        user_id=user.id,
        name="test-client",
        key_hash=hash_secret(raw_key),
        is_active=True,
    )
    record.user = user
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = record

    authenticated = asyncio.run(dependency(raw_key, session))

    assert authenticated is user


def test_query_api_key_is_required() -> None:
    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(APIKeyRequiredError):
        asyncio.run(get_current_query_api_key_user(None, session))
