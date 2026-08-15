from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.models.user import User


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    query = select(User).where(User.email == email)
    return await session.scalar(query)


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    hashed_password: str,
    full_name: str | None = None,
    is_active: bool = True,
    is_superuser: bool = False,
    email_verified_at: datetime | None = None,
    email_verification_token_hash: str | None = None,
    email_verification_expires_at: datetime | None = None,
    email_verification_requested_at: datetime | None = None,
) -> User:
    user = User(
        email=email,
        hashed_password=hashed_password,
        full_name=full_name,
        is_active=is_active,
        is_superuser=is_superuser,
        email_verified_at=email_verified_at,
        email_verification_token_hash=email_verification_token_hash,
        email_verification_expires_at=email_verification_expires_at,
        email_verification_requested_at=email_verification_requested_at,
    )

    session.add(user)
    await session.flush()

    return user
