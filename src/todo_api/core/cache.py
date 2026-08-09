from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from inspect import signature
from typing import Any

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from pydantic import BaseModel
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from todo_api.core.config import Settings

CACHE_STATUS_HEADER = "X-FastAPI-Cache"
TODO_CACHE_NAMESPACE = "todos"

logger = logging.getLogger(__name__)


def initialize_cache(settings: Settings) -> None:
    """Configure a fresh process-local cache for this application lifespan."""

    FastAPICache.reset()
    FastAPICache.init(
        InMemoryBackend(),
        prefix=settings.cache_prefix,
        expire=settings.cache_ttl_seconds,
        cache_status_header=CACHE_STATUS_HEADER,
        enable=settings.cache_enabled,
    )


async def close_cache() -> None:
    """Release cached values and reset fastapi-cache2's process-global state."""

    try:
        await FastAPICache.clear()
    finally:
        FastAPICache.reset()


def todo_cache_key_builder(
    function: Callable[..., Any],
    namespace: str = "",
    *,
    request: Request | None = None,
    response: Response | None = None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    """Build a stable cache key scoped to the authenticated todo owner."""

    del request, response

    arguments = signature(function).bind_partial(*args, **kwargs).arguments
    current_user = arguments.get("current_user")
    user_id = getattr(current_user, "id", None)

    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("Todo cache keys require an authenticated user ID.")

    query = arguments.get("query")
    query_values = query.model_dump(mode="json") if isinstance(query, BaseModel) else None
    key_data = {
        "endpoint": f"{function.__module__}.{function.__qualname__}",
        "query": query_values,
        "todo_id": arguments.get("todo_id"),
    }
    serialized = json.dumps(key_data, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode()).hexdigest()

    return f"{namespace}:user:{user_id}:{digest}"


async def invalidate_todo_cache(user_id: int) -> None:
    """Best-effort invalidation for all cached todo reads owned by one user."""

    try:
        await FastAPICache.clear(namespace=f"{TODO_CACHE_NAMESPACE}:user:{user_id}")
    except Exception:
        # A cache failure must not turn an already-committed database write into
        # an error response. The short TTL bounds any stale entry that remains.
        logger.warning("Failed to invalidate todo cache for user %s.", user_id, exc_info=True)


class PrivateCacheHeadersMiddleware:
    """Prevent authenticated cache responses from entering shared HTTP caches."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_private_cache_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if CACHE_STATUS_HEADER in headers:
                    headers["Cache-Control"] = "private, no-store"
                    if "ETag" in headers:
                        del headers["ETag"]
                    headers.add_vary_header("Authorization")
                    headers.add_vary_header("Cookie")

            await send(message)

        await self.app(scope, receive, send_private_cache_headers)
