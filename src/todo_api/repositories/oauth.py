from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.models.oauth_authorization_code import OAuthAuthorizationCode


async def create_authorization_code(
    session: AsyncSession,
    *,
    code_hash: str,
    user_id: int,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    expires_at: datetime,
) -> OAuthAuthorizationCode:
    record = OAuthAuthorizationCode(
        code_hash=code_hash,
        user_id=user_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        expires_at=expires_at,
    )
    session.add(record)
    await session.flush()
    return record


async def prune_expired_authorization_codes(
    session: AsyncSession,
    *,
    expired_at: datetime,
) -> None:
    await session.execute(
        delete(OAuthAuthorizationCode).where(
            OAuthAuthorizationCode.expires_at <= expired_at,
        )
    )


async def consume_authorization_code(
    session: AsyncSession,
    *,
    code_hash: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    consumed_at: datetime,
) -> int | None:
    """Atomically validate and mark a one-time authorization code consumed."""

    return await session.scalar(
        update(OAuthAuthorizationCode)
        .where(
            OAuthAuthorizationCode.code_hash == code_hash,
            OAuthAuthorizationCode.client_id == client_id,
            OAuthAuthorizationCode.redirect_uri == redirect_uri,
            OAuthAuthorizationCode.code_challenge == code_challenge,
            OAuthAuthorizationCode.expires_at > consumed_at,
            OAuthAuthorizationCode.consumed_at.is_(None),
        )
        .values(consumed_at=consumed_at)
        .returning(OAuthAuthorizationCode.user_id)
    )
