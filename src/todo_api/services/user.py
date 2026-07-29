from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.exceptions.user import (
    AccountDeactivationUnavailableError,
    ProfileUpdateUnavailableError,
)
from todo_api.models.user import User
from todo_api.schemas.user import UserProfileUpdateSchema


@dataclass(slots=True)
class UserService:
    session: AsyncSession

    async def update_profile(
        self,
        user: User,
        payload: UserProfileUpdateSchema,
    ) -> User:
        """Update the editable fields on the current user's profile."""

        user.full_name = payload.full_name

        try:
            await self.session.flush()
            await self.session.refresh(user)
            await self.session.commit()
        except SQLAlchemyError as exc:
            raise ProfileUpdateUnavailableError() from exc

        return user

    async def deactivate_account(self, user: User) -> None:
        """Deactivate the current account and invalidate its credentials."""

        if not user.is_active:
            return

        user.is_active = False

        try:
            await self.session.commit()
        except SQLAlchemyError as exc:
            raise AccountDeactivationUnavailableError() from exc
