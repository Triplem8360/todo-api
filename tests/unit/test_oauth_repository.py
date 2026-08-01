from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.models.oauth_authorization_code import OAuthAuthorizationCode
from todo_api.repositories.oauth import (
    consume_authorization_code,
    create_authorization_code,
    prune_expired_authorization_codes,
)


def test_create_authorization_code_adds_and_flushes_the_record() -> None:
    session = AsyncMock(spec=AsyncSession)
    expires_at = datetime.now(UTC) + timedelta(minutes=2)

    record = asyncio.run(
        create_authorization_code(
            session,
            code_hash="a" * 64,
            user_id=7,
            client_id="public-client",
            redirect_uri="https://client.example/callback",
            code_challenge="A" * 43,
            expires_at=expires_at,
        )
    )

    assert isinstance(record, OAuthAuthorizationCode)
    assert record.expires_at == expires_at
    assert record.consumed_at is None
    session.add.assert_called_once_with(record)
    session.flush.assert_awaited_once()


def test_consume_authorization_code_updates_instead_of_deleting() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = 7
    now = datetime.now(UTC)

    user_id = asyncio.run(
        consume_authorization_code(
            session,
            code_hash="a" * 64,
            client_id="public-client",
            redirect_uri="https://client.example/callback",
            code_challenge="A" * 43,
            consumed_at=now,
        )
    )

    statement = session.scalar.await_args.args[0]
    assert user_id == 7
    assert statement.is_update
    assert "consumed_at IS NULL" in str(statement)
    assert statement.compile().params["consumed_at"] == now


def test_prune_expired_authorization_codes_uses_the_expiration_index() -> None:
    session = AsyncMock(spec=AsyncSession)

    asyncio.run(
        prune_expired_authorization_codes(
            session,
            expired_at=datetime.now(UTC),
        )
    )

    statement = session.execute.await_args.args[0]
    assert statement.is_delete
    assert "expires_at" in str(statement)
