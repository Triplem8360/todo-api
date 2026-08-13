from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from todo_api.core.config import Settings
from todo_api.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        app_debug=False,
        cache_backend="memory",
        database_url="postgresql+asyncpg://todo:todo@localhost:5432/todo_test",
        secret_key="test-secret-key-with-at-least-thirty-two-bytes",
    )


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    app = create_app()

    with TestClient(app) as test_client:
        yield test_client
