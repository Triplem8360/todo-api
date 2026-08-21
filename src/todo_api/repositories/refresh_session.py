from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.models.refresh_session import RefreshSession


async def prune_expired_refresh_sessions(session: AsyncSession, *, expired_at: datetime) -> int:
    result = await session.execute(
        delete(RefreshSession).where(
            RefreshSession.expires_at <= expired_at,
        )
    )
    rowcount = getattr(result, "rowcount", 0)
    return max(rowcount, 0) if isinstance(rowcount, int) else 0
