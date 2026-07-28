from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.core.security import generate_api_key, hash_secret
from todo_api.exceptions.api_key import (
    APIKeyCreationUnavailableError,
    APIKeyListUnavailableError,
    APIKeyNotFoundError,
    APIKeyRevocationUnavailableError,
)
from todo_api.models.api_key import APIKey
from todo_api.repositories.api_key import (
    create_api_key_record,
    get_user_api_key_by_id,
    list_user_api_keys,
)
from todo_api.schemas.api_key import APIKeyCreatedResponseSchema


async def issue_api_key(
    session: AsyncSession,
    *,
    user_id: int,
    name: str,
) -> APIKeyCreatedResponseSchema:
    """Create an API key and return its plaintext value exactly once."""

    raw_key = generate_api_key()
    try:
        record = await create_api_key_record(
            session,
            user_id=user_id,
            name=name,
            key_hash=hash_secret(raw_key),
        )
        await session.commit()
    except SQLAlchemyError as exc:
        raise APIKeyCreationUnavailableError() from exc

    return APIKeyCreatedResponseSchema(
        id=record.id,
        name=record.name,
        is_active=record.is_active,
        created_at=record.created_at,
        api_key=raw_key,
    )


async def list_api_keys(
    session: AsyncSession,
    *,
    user_id: int,
    include_revoked: bool = False,
) -> list[APIKey]:
    """Return API keys owned by a user."""

    try:
        return await list_user_api_keys(
            session,
            user_id=user_id,
            include_revoked=include_revoked,
        )
    except SQLAlchemyError as exc:
        raise APIKeyListUnavailableError() from exc


async def revoke_api_key(
    session: AsyncSession,
    *,
    user_id: int,
    api_key_id: int,
) -> None:
    """Idempotently revoke an API key owned by a user."""

    try:
        record = await get_user_api_key_by_id(
            session,
            user_id=user_id,
            api_key_id=api_key_id,
        )
    except SQLAlchemyError as exc:
        raise APIKeyRevocationUnavailableError() from exc

    if record is None:
        raise APIKeyNotFoundError()
    if not record.is_active:
        return

    record.is_active = False
    try:
        await session.commit()
    except SQLAlchemyError as exc:
        raise APIKeyRevocationUnavailableError() from exc
