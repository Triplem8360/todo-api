from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.exceptions.api_key import (
    APIKeyListUnavailableError,
    APIKeyNotFoundError,
)
from todo_api.models.api_key import APIKey
from todo_api.services.api_key import issue_api_key, list_api_keys, revoke_api_key


def api_key_record(*, active: bool = True) -> APIKey:
    return APIKey(
        id=1,
        user_id=1,
        name="test-client",
        key_hash="a" * 64,
        is_active=active,
        created_at=datetime.now(UTC),
    )


def test_issue_api_key_returns_plaintext_once() -> None:
    session = AsyncMock(spec=AsyncSession)
    record = api_key_record()

    with patch(
        "todo_api.services.api_key.create_api_key_record",
        new=AsyncMock(return_value=record),
    ) as create_record:
        response = asyncio.run(issue_api_key(session, user_id=record.user_id, name=record.name))

    assert response.api_key.startswith("todo_")
    assert create_record.await_args.kwargs["key_hash"] != response.api_key
    assert len(create_record.await_args.kwargs["key_hash"]) == 64
    session.commit.assert_awaited_once()


def test_list_api_keys_maps_database_failure() -> None:
    session = AsyncMock(spec=AsyncSession)
    with (
        patch(
            "todo_api.services.api_key.list_user_api_keys",
            new=AsyncMock(side_effect=SQLAlchemyError("database unavailable")),
        ),
        pytest.raises(APIKeyListUnavailableError),
    ):
        asyncio.run(list_api_keys(session, user_id=1))


def test_revoke_api_key_requires_owned_record() -> None:
    session = AsyncMock(spec=AsyncSession)
    with patch(
        "todo_api.services.api_key.get_user_api_key_by_id",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(APIKeyNotFoundError):
            asyncio.run(revoke_api_key(session, user_id=1, api_key_id=99))

    session.commit.assert_not_awaited()


def test_revoke_api_key_is_idempotent() -> None:
    session = AsyncMock(spec=AsyncSession)
    record = api_key_record(active=False)
    with patch(
        "todo_api.services.api_key.get_user_api_key_by_id",
        new=AsyncMock(return_value=record),
    ):
        asyncio.run(revoke_api_key(session, user_id=1, api_key_id=record.id))

    session.commit.assert_not_awaited()
