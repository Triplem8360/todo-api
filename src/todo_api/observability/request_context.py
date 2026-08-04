from __future__ import annotations

from time import perf_counter
from uuid import UUID, uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

PROCESS_TIME_HEADER = "X-Process-Time"
REQUEST_ID_HEADER = "X-Request-ID"


def resolve_request_id(value: str | None) -> str:
    if value is None:
        return str(uuid4())

    try:
        return str(UUID(value))
    except ValueError:
        return str(uuid4())


class RequestContextMiddleware:
    """
    Add request correlation and processing-time headers.

    The request ID is also exposed through:

        request.state.request_id
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_headers = Headers(scope=scope)
        request_id = resolve_request_id(request_headers.get(REQUEST_ID_HEADER))

        state = scope.setdefault("state", {})
        state["request_id"] = request_id

        started_at = perf_counter()

        async def send_with_observability_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                process_time = perf_counter() - started_at
                response_headers = MutableHeaders(scope=message)

                response_headers[PROCESS_TIME_HEADER] = f"{process_time:.6f}"
                response_headers[REQUEST_ID_HEADER] = request_id

            await send(message)

        await self.app(scope, receive, send_with_observability_headers)
