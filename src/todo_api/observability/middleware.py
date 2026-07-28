from __future__ import annotations

from time import perf_counter
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from todo_api.observability.metrics import AppMetrics


def route_template(scope: Scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    if not path:
        return "__unmatched__"

    root_path = str(scope.get("root_path", "")).rstrip("/")
    return f"{root_path}{path}"


class HTTPMetricsMiddleware:
    def __init__(self, app: ASGIApp, *, metrics: AppMetrics, metrics_path: str) -> None:
        self.app = app
        self.metrics = metrics
        self.metrics_path = metrics_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == self.metrics_path:
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "UNKNOWN")).upper()
        status_code = 500
        request_size = 0
        response_size = 0
        started_at = perf_counter()
        self.metrics.http_requests_in_progress.labels(method=method).inc()

        async def receive_with_size() -> Message:
            nonlocal request_size
            message = await receive()
            if message["type"] == "http.request":
                request_size += len(message.get("body", b""))
            return message

        async def send_with_size(message: Message) -> None:
            nonlocal response_size, status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            elif message["type"] == "http.response.body":
                response_size += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive_with_size, send_with_size)
        except Exception as exc:
            self.metrics.http_exceptions_total.labels(
                method=method,
                route=route_template(scope),
                exception_type=type(exc).__name__,
            ).inc()
            raise
        finally:
            route = route_template(scope)
            self.metrics.http_requests_in_progress.labels(method=method).dec()
            self.metrics.http_requests_total.labels(
                method=method,
                route=route,
                status_code=str(status_code),
            ).inc()
            self.metrics.http_request_duration_seconds.labels(
                method=method,
                route=route,
            ).observe(perf_counter() - started_at)
            self.metrics.http_request_size_bytes.labels(method=method, route=route).observe(
                request_size
            )
            self.metrics.http_response_size_bytes.labels(method=method, route=route).observe(
                response_size
            )
