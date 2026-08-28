from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.exceptions.user import (
    AccountDeactivationUnavailableError,
    ProfileUpdateUnavailableError,
)
from todo_api.models.user import User
from todo_api.schemas.user import UserProfileUpdateSchema
from todo_api.services.user import UserService


def active_user() -> User:
    return User(
        id=1,
        email="user@example.com",
        full_name="Old Name",
        hashed_password="password-hash",
        is_active=True,
        is_superuser=False,
    )


def test_update_user_profile_normalizes_name_and_commits() -> None:
    user = active_user()
    session = AsyncMock(spec=AsyncSession)
    service = UserService(session=session)
    payload = UserProfileUpdateSchema(full_name="  New   Name  ")

    updated = asyncio.run(service.update_profile(user, payload))

    assert updated is user
    assert user.full_name == "New Name"
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(user)
    session.commit.assert_awaited_once()


def test_update_user_profile_maps_database_failure() -> None:
    user = active_user()
    session = AsyncMock(spec=AsyncSession)
    service = UserService(session=session)
    session.flush.side_effect = SQLAlchemyError("database unavailable")

    with pytest.raises(ProfileUpdateUnavailableError):
        asyncio.run(service.update_profile(user, UserProfileUpdateSchema(full_name=None)))


def test_deactivate_user_account() -> None:
    user = active_user()
    session = AsyncMock(spec=AsyncSession)
    service = UserService(session=session)

    asyncio.run(service.deactivate_account(user))

    assert user.is_active is False
    session.commit.assert_awaited_once()


def test_deactivate_user_account_maps_database_failure() -> None:
    user = active_user()
    session = AsyncMock(spec=AsyncSession)
    service = UserService(session=session)
    session.commit.side_effect = SQLAlchemyError("database unavailable")

    with pytest.raises(AccountDeactivationUnavailableError):
        asyncio.run(service.deactivate_account(user))
