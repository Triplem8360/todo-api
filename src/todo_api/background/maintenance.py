from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from todo_api.db.session import Database
from todo_api.repositories.oauth import (
    prune_expired_authorization_codes,
)
from todo_api.repositories.refresh_session import (
    prune_expired_refresh_sessions,
)
from todo_api.repositories.todo import archive_completed_todos
from todo_api.repositories.user import clear_expired_email_verification_tokens

logger = logging.getLogger(__name__)


async def prune_oauth_authorization_codes(database: Database) -> int:
    now = datetime.now(UTC)

    async with database.session_factory() as session, session.begin():
        deleted = await prune_expired_authorization_codes(session, expired_at=now)

    logger.info("Expired OAuth authorization codes pruned", extra={"deleted_count": deleted})
    return deleted


async def prune_refresh_sessions(database: Database) -> int:
    now = datetime.now(UTC)

    async with database.session_factory() as session, session.begin():
        deleted = await prune_expired_refresh_sessions(session, expired_at=now)

    logger.info("Expired refresh sessions pruned", extra={"deleted_count": deleted})
    return deleted


async def clear_expired_verification_tokens(database: Database) -> int:
    now = datetime.now(UTC)

    async with database.session_factory() as session, session.begin():
        cleared = await clear_expired_email_verification_tokens(session, expired_at=now)

    logger.info("Expired email verification tokens cleared", extra={"cleared_count": cleared})
    return cleared


async def auto_archive_completed_todos(database: Database, *, after_days: int) -> int:
    if after_days == 0:
        logger.info("Completed Todo auto-archiving is disabled")
        return 0

    completed_before = datetime.now(UTC) - timedelta(days=after_days)
    async with database.session_factory() as session, session.begin():
        archived = await archive_completed_todos(
            session,
            completed_before=completed_before,
        )

    logger.info(
        "Old completed Todos archived",
        extra={"archived_count": archived, "auto_archive_after_days": after_days},
    )
    return archived
