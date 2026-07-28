from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.exceptions.user import (
    AccountDeactivationUnavailableError,
    ProfileUpdateUnavailableError,
)
from todo_api.models.user import User
from todo_api.schemas.user import UserProfileUpdateSchema


async def update_user_profile(
    session: AsyncSession,
    user: User,
    payload: UserProfileUpdateSchema,
) -> User:
    """Update the editable fields on the current user's profile."""

    user.full_name = payload.full_name
    try:
        await session.flush()
        await session.refresh(user)
        await session.commit()
    except SQLAlchemyError as exc:
        raise ProfileUpdateUnavailableError() from exc

    return user


async def deactivate_user_account(session: AsyncSession, user: User) -> None:
    """Deactivate the current account, invalidating all of its credentials."""

    if not user.is_active:
        return

    user.is_active = False
    try:
        await session.commit()
    except SQLAlchemyError as exc:
        raise AccountDeactivationUnavailableError() from exc
