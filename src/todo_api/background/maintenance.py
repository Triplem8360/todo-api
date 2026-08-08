from __future__ import annotations

import logging
from datetime import UTC, datetime

from todo_api.db.session import Database
from todo_api.repositories.oauth import (
    prune_expired_authorization_codes,
)
from todo_api.repositories.refresh_session import (
    prune_expired_refresh_sessions,
)

logger = logging.getLogger(__name__)


async def prune_oauth_authorization_codes(database: Database) -> None:
    now = datetime.now(UTC)

    async with database.session_factory() as session, session.begin():
        await prune_expired_authorization_codes(session, expired_at=now)

    logger.info("Expired OAuth authorization codes pruned")


async def prune_refresh_sessions(database: Database) -> None:
    now = datetime.now(UTC)

    async with database.session_factory() as session, session.begin():
        await prune_expired_refresh_sessions(session, expired_at=now)

    logger.info("Expired refresh sessions pruned")
