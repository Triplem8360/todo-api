from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Message, Receive, Scope, Send

from todo_api.api.v1.routes.todos import get_todo, list_todos
from todo_api.core.cache import (
    CACHE_STATUS_HEADER,
    PrivateCacheHeadersMiddleware,
    close_cache,
    initialize_cache,
    invalidate_todo_cache,
    todo_cache_key_builder,
)
from todo_api.core.config import Settings
from todo_api.models.todo import Todo, TodoPriority, TodoStatus
from todo_api.schemas.todo import (
    TodoListQuerySchema,
    TodoListResponseSchema,
    TodoResponseSchema,
)
from todo_api.services.todo import TodoService


def _request(path: str = "/api/v1/todos") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"limit=20&offset=0",
            "headers": [],
            "client": ("testclient", 50_000),
            "server": ("testserver", 80),
        }
    )


def _cache_settings(*, enabled: bool = True) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        secret_key="test-secret-key-with-at-least-thirty-two-bytes",
        cache_enabled=enabled,
        cache_ttl_seconds=60,
    )


def test_todo_cache_key_is_stable_and_user_scoped() -> None:
    def endpoint(
        query: TodoListQuerySchema,
        current_user: SimpleNamespace,
    ) -> None:
        del query, current_user

    query = TodoListQuerySchema()
    first_key = todo_cache_key_builder(
        endpoint,
        "todo-api:todos",
        args=(),
        kwargs={"query": query, "current_user": SimpleNamespace(id=1)},
    )
    equivalent_key = todo_cache_key_builder(
        endpoint,
        "todo-api:todos",
        args=(),
        kwargs={"query": TodoListQuerySchema(), "current_user": SimpleNamespace(id=1)},
    )
    other_user_key = todo_cache_key_builder(
        endpoint,
        "todo-api:todos",
        args=(),
        kwargs={"query": query, "current_user": SimpleNamespace(id=2)},
    )
    other_query_key = todo_cache_key_builder(
        endpoint,
        "todo-api:todos",
        args=(),
        kwargs={
            "query": TodoListQuerySchema(limit=50),
            "current_user": SimpleNamespace(id=1),
        },
    )

    assert first_key == equivalent_key
    assert ":user:1:" in first_key
    assert first_key != other_user_key
    assert first_key != other_query_key


def test_todo_cache_hits_and_invalidates_only_the_mutating_user() -> None:
    async def exercise_cache() -> None:
        initialize_cache(_cache_settings())
        service = Mock(spec=TodoService)
        service.list = AsyncMock(
            return_value=TodoListResponseSchema(items=[], total=0, limit=20, offset=0)
        )
        query = TodoListQuerySchema()

        async def call(user_id: int) -> Response:
            response = Response()
            await list_todos(
                query=query,
                service=service,
                current_user=SimpleNamespace(id=user_id),
                __fastapi_cache_request=_request(),
                __fastapi_cache_response=response,
            )
            return response

        try:
            first_user_miss = await call(1)
            first_user_hit = await call(1)
            second_user_miss = await call(2)

            assert first_user_miss.headers["X-FastAPI-Cache"] == "MISS"
            assert first_user_hit.headers["X-FastAPI-Cache"] == "HIT"
            assert second_user_miss.headers["X-FastAPI-Cache"] == "MISS"
            assert service.list.await_count == 2

            await invalidate_todo_cache(1)

            first_user_after_write = await call(1)
            second_user_after_write = await call(2)

            assert first_user_after_write.headers["X-FastAPI-Cache"] == "MISS"
            assert second_user_after_write.headers["X-FastAPI-Cache"] == "HIT"
            assert service.list.await_count == 3
        finally:
            await close_cache()

    asyncio.run(exercise_cache())


def test_todo_detail_cache_stores_only_the_response_schema() -> None:
    async def exercise_cache() -> None:
        initialize_cache(_cache_settings())
        now = datetime.now(UTC)
        todo = Todo(
            id=10,
            user_id=1,
            title="Cached todo",
            description=None,
            status=TodoStatus.TODO,
            priority=TodoPriority.MEDIUM,
            due_at=None,
            completed_at=None,
            is_archived=False,
            created_at=now,
            updated_at=now,
        )
        service = Mock(spec=TodoService)
        service.get = AsyncMock(return_value=todo)

        async def call() -> object:
            return await get_todo(
                todo_id=todo.id,
                service=service,
                current_user=SimpleNamespace(id=todo.user_id),
                __fastapi_cache_request=_request(f"/api/v1/todos/{todo.id}"),
                __fastapi_cache_response=Response(),
            )

        try:
            first_result = await call()
            cached_result = await call()

            assert service.get.await_count == 1
            assert isinstance(first_result, TodoResponseSchema)
            assert first_result.id == todo.id
            assert isinstance(cached_result, dict)
            assert cached_result["id"] == todo.id
            assert "user_id" not in cached_result
        finally:
            await close_cache()

    asyncio.run(exercise_cache())


def test_cache_can_be_disabled_without_changing_endpoints() -> None:
    async def exercise_disabled_cache() -> None:
        initialize_cache(_cache_settings(enabled=False))
        service = Mock(spec=TodoService)
        service.list = AsyncMock(
            return_value=TodoListResponseSchema(items=[], total=0, limit=20, offset=0)
        )
        query = TodoListQuerySchema()

        try:
            for _ in range(2):
                await list_todos(
                    query=query,
                    service=service,
                    current_user=SimpleNamespace(id=1),
                    __fastapi_cache_request=_request(),
                    __fastapi_cache_response=Response(),
                )

            assert service.list.await_count == 2
        finally:
            await close_cache()

    asyncio.run(exercise_disabled_cache())


def test_cached_http_responses_are_private_and_vary_by_credentials() -> None:
    sent_messages: list[Message] = []

    async def cached_response(
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        del scope, receive
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"cache-control", b"max-age=60"),
                    (b"etag", b'W/"cached-value"'),
                    (CACHE_STATUS_HEADER.lower().encode(), b"HIT"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"{}"})

    async def exercise_middleware() -> None:
        middleware = PrivateCacheHeadersMiddleware(cached_response)

        async def receive() -> Message:
            return {"type": "http.request"}

        async def send(message: Message) -> None:
            sent_messages.append(message)

        await middleware(
            {"type": "http", "method": "GET", "path": "/api/v1/todos"},
            receive,
            send,
        )

    asyncio.run(exercise_middleware())

    headers = Headers(raw=sent_messages[0]["headers"])
    assert headers["cache-control"] == "private, no-store"
    assert "etag" not in headers
    assert headers["vary"] == "Authorization, Cookie"
