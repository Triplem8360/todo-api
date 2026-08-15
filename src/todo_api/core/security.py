from __future__ import annotations

import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, TypeVar

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import ValidationError

from todo_api.core.config import Settings
from todo_api.exceptions.auth import InvalidAccessTokenError, InvalidRefreshTokenError
from todo_api.schemas.token import (
    AccessTokenPayload,
    RefreshTokenPayload,
    TokenResponseSchema,
)

ACCESS_TOKEN_CLAIMS = ("sub", "exp", "iat", "jti", "iss", "aud", "type")
REFRESH_TOKEN_CLAIMS = (*ACCESS_TOKEN_CLAIMS, "sid")
API_KEY_HEADER = "X-API-Key"
CSRF_TOKEN_HEADER = "X-CSRF-Token"

_PASSWORD_HASHER = PasswordHash.recommended()
_TOKEN_BYTES = 32
PayloadT = TypeVar("PayloadT", AccessTokenPayload, RefreshTokenPayload)


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_and_update_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    return _PASSWORD_HASHER.verify_and_update(password, password_hash)


def verify_password(password: str, password_hash: str) -> bool:
    return _PASSWORD_HASHER.verify(password, password_hash)


DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-protection")


def hash_secret(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def verify_csrf_token(header_token: str | None, cookie_token: str | None) -> bool:
    """Compare double-submit CSRF tokens in constant time."""

    if not header_token or not cookie_token:
        return False

    return secrets.compare_digest(header_token, cookie_token)


def generate_api_key() -> str:
    return f"todo_{secrets.token_urlsafe(_TOKEN_BYTES)}"


def generate_token_id() -> str:
    return secrets.token_hex(_TOKEN_BYTES)


def generate_email_verification_token() -> str:
    """Return a high-entropy opaque token suitable for an emailed URL."""

    return secrets.token_urlsafe(_TOKEN_BYTES)


def _required(value: str, name: str) -> str:
    if normalized := value.strip():
        return normalized
    raise ValueError(f"{name} cannot be empty.")


def _lifetime(custom: timedelta | None, default: timedelta, name: str) -> timedelta:
    lifetime = custom if custom is not None else default
    if lifetime <= timedelta(0):
        raise ValueError(f"{name} lifetime must be positive.")
    return lifetime


def _encode(payload: AccessTokenPayload | RefreshTokenPayload, settings: Settings) -> str:
    return jwt.encode(
        payload.model_dump(mode="python", by_alias=True),
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def _access_token_lifetime(
    settings: Settings,
    custom: timedelta | None = None,
) -> timedelta:
    return _lifetime(
        custom=custom,
        default=timedelta(minutes=settings.access_token_expire_minutes),
        name="Access token",
    )


def _refresh_token_lifetime(
    settings: Settings,
    custom: timedelta | None = None,
) -> timedelta:
    return _lifetime(
        custom=custom,
        default=timedelta(days=settings.refresh_token_expire_days),
        name="Refresh token",
    )


def _bounded_lifetime(
    lifetime: timedelta,
    *,
    issued_at: datetime,
    absolute_expires_at: datetime | None,
    name: str,
) -> timedelta:
    """Restrict a token lifetime to an optional absolute deadline."""

    if absolute_expires_at is None:
        return lifetime

    if absolute_expires_at.tzinfo is None or absolute_expires_at.utcoffset() is None:
        raise ValueError(f"{name} absolute expiration must be timezone-aware.")

    remaining = absolute_expires_at - issued_at

    if remaining <= timedelta(0):
        raise ValueError(f"{name} absolute expiration must be in the future.")

    return min(lifetime, remaining)


def create_access_token(
    subject: str,
    settings: Settings,
    expires_delta: timedelta | None = None,
    *,
    issued_at: datetime | None = None,
) -> str:
    issued_at = issued_at or datetime.now(UTC)
    lifetime = _access_token_lifetime(settings, expires_delta)
    return _encode(
        AccessTokenPayload(
            sub=_required(subject, "Token subject"),
            exp=issued_at + lifetime,
            iat=issued_at,
            jti=generate_token_id(),
            iss=settings.jwt_issuer,
            aud=settings.jwt_access_audience,
            type="access",
        ),
        settings,
    )


def create_refresh_token(
    subject: str,
    session_id: str,
    settings: Settings,
    expires_delta: timedelta | None = None,
    *,
    issued_at: datetime | None = None,
) -> str:
    issued_at = issued_at or datetime.now(UTC)
    lifetime = _refresh_token_lifetime(settings, expires_delta)
    return _encode(
        RefreshTokenPayload(
            sub=_required(subject, "Token subject"),
            exp=issued_at + lifetime,
            iat=issued_at,
            jti=generate_token_id(),
            sid=_required(session_id, "Session ID"),
            iss=settings.jwt_issuer,
            aud=settings.jwt_refresh_audience,
            type="refresh",
        ),
        settings,
    )


def create_token_pair(
    subject: str,
    session_id: str,
    settings: Settings,
    *,
    issued_at: datetime | None = None,
    absolute_expires_at: datetime | None = None,
) -> TokenResponseSchema:
    issued_at = issued_at or datetime.now(UTC)

    access_lifetime = _bounded_lifetime(
        _access_token_lifetime(settings),
        issued_at=issued_at,
        absolute_expires_at=absolute_expires_at,
        name="Access token",
    )

    refresh_lifetime = _bounded_lifetime(
        _refresh_token_lifetime(settings),
        issued_at=issued_at,
        absolute_expires_at=absolute_expires_at,
        name="Refresh token",
    )

    return TokenResponseSchema(
        access_token=create_access_token(
            subject,
            settings,
            expires_delta=access_lifetime,
            issued_at=issued_at,
        ),
        refresh_token=create_refresh_token(
            subject,
            session_id,
            settings,
            expires_delta=refresh_lifetime,
            issued_at=issued_at,
        ),
        # Token responses express expires_in in seconds.
        expires_in=int(access_lifetime.total_seconds()),
    )


def _decode(
    token: str,
    *,
    audience: str,
    required_claims: Sequence[str],
    payload_model: type[PayloadT],
    error_type: type[InvalidAccessTokenError | InvalidRefreshTokenError],
    settings: Settings,
) -> PayloadT:
    try:
        decoded: dict[str, Any] = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=audience,
            options={"require": list(required_claims), "strict_aud": True},
        )
        return payload_model.model_validate(decoded)
    except (InvalidTokenError, ValidationError) as exc:
        raise error_type() from exc


def decode_access_token(token: str, settings: Settings) -> AccessTokenPayload:
    return _decode(
        token,
        audience=settings.jwt_access_audience,
        required_claims=ACCESS_TOKEN_CLAIMS,
        payload_model=AccessTokenPayload,
        error_type=InvalidAccessTokenError,
        settings=settings,
    )


def decode_refresh_token(token: str, settings: Settings) -> RefreshTokenPayload:
    return _decode(
        token,
        audience=settings.jwt_refresh_audience,
        required_claims=REFRESH_TOKEN_CLAIMS,
        payload_model=RefreshTokenPayload,
        error_type=InvalidRefreshTokenError,
        settings=settings,
    )
