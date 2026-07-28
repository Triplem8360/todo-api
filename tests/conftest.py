from __future__ import annotations

import pytest

from todo_api.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        app_debug=False,
        database_url="postgresql+asyncpg://todo:todo@localhost:5432/todo_test",
        secret_key="test-secret-key-with-at-least-thirty-two-bytes",
    )
