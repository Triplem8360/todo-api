from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from anyio import to_thread
from argon2.exceptions import HashingError
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.core.config import Settings
from todo_api.core.security import (
    DUMMY_PASSWORD_HASH,
    create_token_pair,
    decode_refresh_token,
    generate_token_id,
    hash_password,
    hash_secret,
    verify_and_update_password,
)
from todo_api.db.errors import is_constraint_violation
from todo_api.exceptions.auth import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    LoginSessionUnavailableError,
    LogoutUnavailableError,
    RefreshTokenReuseDetectedError,
    RegistrationUnavailableError,
    TokenRefreshUnavailableError,
)
from todo_api.models.refresh_session import RefreshSession
from todo_api.models.user import User
from todo_api.repositories.user import (
    create_user,
    get_user_by_email,
    get_user_by_id,
)
from todo_api.schemas.token import TokenResponseSchema
from todo_api.schemas.user import UserCreateSchema
from todo_api.utils.email import normalize_email


@dataclass(slots=True)
class AuthService:
    session: AsyncSession
    settings: Settings

    async def register(self, payload: UserCreateSchema, *, is_superuser: bool = False) -> User:
        """Register a user with a stable duplicate-email response."""

        try:
            existing_user = await get_user_by_email(self.session, str(payload.email))
        except SQLAlchemyError as exc:
            raise RegistrationUnavailableError() from exc

        if existing_user is not None:
            raise EmailAlreadyRegisteredError()

        try:
            password_hash = await to_thread.run_sync(
                hash_password,
                payload.password.get_secret_value(),
            )
        except HashingError as exc:
            raise RegistrationUnavailableError() from exc

        try:
            user = await create_user(
                self.session,
                email=str(payload.email),
                full_name=payload.full_name,
                hashed_password=password_hash,
                is_superuser=is_superuser,
            )
            await self.session.commit()
        except IntegrityError as exc:
            if is_constraint_violation(exc, "uq_users_email"):
                raise EmailAlreadyRegisteredError() from exc

            raise RegistrationUnavailableError() from exc
        except SQLAlchemyError as exc:
            raise RegistrationUnavailableError() from exc

        return user

    async def authenticate(self, email: str, password: str) -> User:
        """Validate password credentials with unknown-user timing protection."""

        try:
            user = await get_user_by_email(self.session, normalize_email(email))
        except SQLAlchemyError as exc:
            raise LoginSessionUnavailableError() from exc

        password_hash = user.hashed_password if user is not None else DUMMY_PASSWORD_HASH

        try:
            valid, replacement_hash = await to_thread.run_sync(
                verify_and_update_password,
                password,
                password_hash,
            )
        except (HashingError, UnknownHashError) as exc:
            raise LoginSessionUnavailableError() from exc

        if user is None or not valid:
            raise InvalidCredentialsError()

        if not user.is_active:
            raise InactiveUserError()

        if replacement_hash is not None:
            user.hashed_password = replacement_hash

        return user

    async def create_login_session(self, user: User) -> TokenResponseSchema:
        """Create an independent login session for the user."""

        now = datetime.now(UTC)
        session_id = generate_token_id()
        absolute_expires_at = now + self.settings.refresh_session_absolute_ttl

        tokens = create_token_pair(
            subject=str(user.id),
            session_id=session_id,
            settings=self.settings,
            issued_at=now,
            absolute_expires_at=absolute_expires_at,
        )

        refresh_payload = decode_refresh_token(tokens.refresh_token, self.settings)

        try:
            self.session.add(
                RefreshSession(
                    id=session_id,
                    user_id=user.id,
                    token_hash=hash_secret(tokens.refresh_token),
                    previous_token_hash=None,
                    expires_at=refresh_payload.exp,
                    absolute_expires_at=absolute_expires_at,
                    last_used_at=now,
                    rotated_at=None,
                )
            )
            await self.session.commit()
        except SQLAlchemyError as exc:
            raise LoginSessionUnavailableError() from exc

        return tokens

    async def refresh_login_session(self, refresh_token: str) -> TokenResponseSchema:
        """Rotate a refresh token and detect reuse outside the grace period."""

        payload = decode_refresh_token(refresh_token, self.settings)

        try:
            user_id = int(payload.sub)
        except (TypeError, ValueError) as exc:
            raise InvalidRefreshTokenError() from exc

        presented_hash = hash_secret(refresh_token)
        now = datetime.now(UTC)

        try:
            record = await self.session.scalar(
                select(RefreshSession)
                .where(RefreshSession.id == payload.session_id)
                .with_for_update()
            )

            if record is None or record.user_id != user_id or not record.is_active(now):
                raise InvalidRefreshTokenError()

            is_current_token = self._matches_token(record.token_hash, presented_hash)
            is_recoverable_retry = not is_current_token and self._is_recoverable_previous_token(
                record,
                presented_hash,
                now,
            )

            if not is_current_token and not is_recoverable_retry:
                record.revoke(now)
                await self.session.commit()
                raise RefreshTokenReuseDetectedError()

            user = await get_user_by_id(self.session, user_id)

            if user is None:
                record.revoke(now)
                await self.session.commit()
                raise InvalidRefreshTokenError()

            if not user.is_active:
                raise InactiveUserError()

            tokens = create_token_pair(
                subject=str(user.id),
                session_id=record.id,
                settings=self.settings,
                issued_at=now,
                absolute_expires_at=record.absolute_expires_at,
            )

            rotated_payload = decode_refresh_token(tokens.refresh_token, self.settings)

            record.rotate(hash_secret(tokens.refresh_token), rotated_payload.exp, now)

            await self.session.commit()
        except SQLAlchemyError as exc:
            raise TokenRefreshUnavailableError() from exc

        return tokens

    async def revoke_refresh_session(self, refresh_token: str) -> None:
        """Idempotently revoke the session represented by a refresh token."""

        try:
            payload = decode_refresh_token(refresh_token, self.settings)
            user_id = int(payload.sub)
        except (InvalidRefreshTokenError, TypeError, ValueError):
            return

        try:
            record = await self.session.scalar(
                select(RefreshSession)
                .where(
                    RefreshSession.id == payload.session_id,
                    RefreshSession.user_id == user_id,
                )
                .with_for_update()
            )

            if record is None or record.revoked_at is not None:
                return

            record.revoke(datetime.now(UTC))
            await self.session.commit()
        except SQLAlchemyError as exc:
            raise LogoutUnavailableError() from exc

    @staticmethod
    def _matches_token(stored_hash: str | None, presented_hash: str) -> bool:
        return stored_hash is not None and secrets.compare_digest(stored_hash, presented_hash)

    def _is_recoverable_previous_token(
        self,
        record: RefreshSession,
        presented_hash: str,
        now: datetime,
    ) -> bool:
        """Accept the previous token only during the configured grace period."""

        grace_period = self.settings.refresh_token_reuse_grace

        if (
            record.previous_token_hash is None
            or record.rotated_at is None
            or grace_period.total_seconds() <= 0
        ):
            return False

        if now > record.rotated_at + grace_period:
            return False

        return self._matches_token(record.previous_token_hash, presented_hash)
