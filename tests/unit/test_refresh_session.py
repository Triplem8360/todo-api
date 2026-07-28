from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from todo_api.models.refresh_session import RefreshSession


def make_session() -> RefreshSession:
    return RefreshSession(
        id="s" * 64,
        user_id=1,
        token_hash="a" * 64,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )


def test_refresh_session_rotation() -> None:
    session = make_session()
    new_expiry = datetime.now(UTC) + timedelta(days=2)

    session.rotate("b" * 64, new_expiry)

    assert session.token_hash == "b" * 64
    assert session.expires_at == new_expiry
    assert session.last_used_at is not None


def test_revoked_session_cannot_rotate() -> None:
    session = make_session()
    session.revoke()

    with pytest.raises(ValueError, match="inactive"):
        session.rotate("b" * 64, datetime.now(UTC) + timedelta(days=2))
