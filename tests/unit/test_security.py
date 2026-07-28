from __future__ import annotations

from datetime import timedelta

import pytest

from todo_api.core.config import Settings
from todo_api.core.security import (
    create_access_token,
    create_refresh_token,
    create_token_pair,
    decode_access_token,
    decode_refresh_token,
    generate_api_key,
    hash_secret,
)
from todo_api.exceptions.auth import InvalidAccessTokenError, InvalidRefreshTokenError


def test_token_pair_round_trip(settings: Settings) -> None:
    settings = settings.model_copy(
        update={
            "access_token_expire_minutes": 2,
            "refresh_token_expire_days": 3,
        }
    )
    tokens = create_token_pair("42", "a" * 64, settings)

    access = decode_access_token(tokens.access_token, settings)
    refresh = decode_refresh_token(tokens.refresh_token, settings)

    assert access.sub == refresh.sub == "42"
    assert access.token_type == "access"
    assert refresh.token_type == "refresh"
    assert refresh.session_id == "a" * 64
    assert access.exp - access.iat == timedelta(minutes=2)
    assert refresh.exp - refresh.iat == timedelta(days=3)
    assert tokens.expires_in == 120


def test_token_types_cannot_be_interchanged(settings: Settings) -> None:
    access = create_access_token("1", settings)
    refresh = create_refresh_token("1", "b" * 64, settings)

    with pytest.raises(InvalidRefreshTokenError):
        decode_refresh_token(access, settings)
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(refresh, settings)


def test_token_lifetime_must_be_positive(settings: Settings) -> None:
    with pytest.raises(ValueError, match="positive"):
        create_access_token("1", settings, timedelta(0))


def test_api_keys_have_prefix_and_stable_hash() -> None:
    key = generate_api_key()

    assert key.startswith("todo_")
    assert len(hash_secret(key)) == 64
    assert hash_secret(key) == hash_secret(key)


def test_production_rejects_placeholder_secret() -> None:
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(
            _env_file=None,
            app_env="production",
            app_debug=False,
            secret_key="change-this-secret-key-in-real-projects",
        )
