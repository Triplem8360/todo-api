from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.repositories.refresh_session import prune_expired_refresh_sessions
from todo_api.repositories.todo import archive_completed_todos
from todo_api.repositories.user import clear_expired_email_verification_tokens


def test_prune_expired_refresh_sessions_returns_deleted_count() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = Mock(rowcount=5)
    now = datetime.now(UTC)

    deleted = asyncio.run(prune_expired_refresh_sessions(session, expired_at=now))

    statement = session.execute.await_args.args[0]
    assert deleted == 5
    assert statement.is_delete
    assert statement.compile().params["expires_at_1"] == now


def test_clear_expired_verification_tokens_only_updates_pending_expired_users() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = Mock(rowcount=2)
    now = datetime.now(UTC)

    cleared = asyncio.run(clear_expired_email_verification_tokens(session, expired_at=now))

    statement = session.execute.await_args.args[0]
    sql = str(statement)
    assert cleared == 2
    assert statement.is_update
    assert "email_verified_at IS NULL" in sql
    assert "email_verification_token_hash IS NOT NULL" in sql
    assert "email_verification_expires_at" in sql


def test_archive_completed_todos_only_updates_old_done_unarchived_rows() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = Mock(rowcount=8)
    cutoff = datetime.now(UTC)

    archived = asyncio.run(archive_completed_todos(session, completed_before=cutoff))

    statement = session.execute.await_args.args[0]
    sql = str(statement)
    assert archived == 8
    assert statement.is_update
    assert "todos.status" in sql
    assert "todos.is_archived IS false" in sql
    assert "todos.completed_at" in sql
