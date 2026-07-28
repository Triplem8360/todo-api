from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from todo_api.models.api_key import APIKey


async def create_api_key_record(
    session: AsyncSession,
    *,
    user_id: int,
    name: str,
    key_hash: str,
) -> APIKey:
    record = APIKey(user_id=user_id, name=name, key_hash=key_hash)
    session.add(record)
    await session.flush()
    return record


async def get_active_api_key_by_hash(
    session: AsyncSession,
    key_hash: str,
) -> APIKey | None:
    query = (
        select(APIKey)
        .options(joinedload(APIKey.user))
        .where(
            APIKey.key_hash == key_hash,
            APIKey.is_active.is_(True),
        )
    )
    return await session.scalar(query)


async def list_user_api_keys(
    session: AsyncSession,
    *,
    user_id: int,
    include_revoked: bool = False,
) -> list[APIKey]:
    query = (
        select(APIKey)
        .where(APIKey.user_id == user_id)
        .order_by(APIKey.created_at.desc(), APIKey.id.desc())
    )

    if not include_revoked:
        query = query.where(APIKey.is_active.is_(True))

    return list(await session.scalars(query))


async def get_user_api_key_by_id(
    session: AsyncSession,
    *,
    user_id: int,
    api_key_id: int,
) -> APIKey | None:
    query = select(APIKey).where(
        APIKey.user_id == user_id,
        APIKey.id == api_key_id,
    )
    return await session.scalar(query)
