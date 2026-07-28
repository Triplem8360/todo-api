from __future__ import annotations

import os
from dataclasses import dataclass

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
    multiprocess,
)
from starlette.responses import Response

HTTP_DURATION_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)
DB_DURATION_BUCKETS = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)
SIZE_BUCKETS = (100, 1_000, 10_000, 100_000, 1_000_000, 10_000_000)


@dataclass(frozen=True, slots=True)
class AppMetrics:
    build_info: Info
    http_requests_total: Counter
    http_request_duration_seconds: Histogram
    http_request_size_bytes: Histogram
    http_response_size_bytes: Histogram
    http_requests_in_progress: Gauge
    http_exceptions_total: Counter
    db_queries_total: Counter
    db_query_duration_seconds: Histogram
    db_queries_in_progress: Gauge
    db_pool_events_total: Counter
    db_pool_connections: Gauge
    db_pool_timeouts_total: Counter
    auth_attempts_total: Counter
    user_registrations_total: Counter


def create_metrics() -> AppMetrics:
    app_metrics = AppMetrics(
        build_info=Info(
            "todo_api_build",
            "Static application build information.",
        ),
        http_requests_total=Counter(
            "todo_api_http_requests_total",
            "Completed HTTP requests.",
            ("method", "route", "status_code"),
        ),
        http_request_duration_seconds=Histogram(
            "todo_api_http_request_duration_seconds",
            "End-to-end HTTP request duration.",
            ("method", "route"),
            buckets=HTTP_DURATION_BUCKETS,
        ),
        http_request_size_bytes=Histogram(
            "todo_api_http_request_size_bytes",
            "HTTP request body size.",
            ("method", "route"),
            buckets=SIZE_BUCKETS,
        ),
        http_response_size_bytes=Histogram(
            "todo_api_http_response_size_bytes",
            "HTTP response body size.",
            ("method", "route"),
            buckets=SIZE_BUCKETS,
        ),
        http_requests_in_progress=Gauge(
            "todo_api_http_requests_in_progress",
            "HTTP requests currently executing.",
            ("method",),
            multiprocess_mode="livesum",
        ),
        http_exceptions_total=Counter(
            "todo_api_http_exceptions_total",
            "Unhandled exceptions escaping the HTTP stack.",
            ("method", "route", "exception_type"),
        ),
        db_queries_total=Counter(
            "todo_api_db_queries_total",
            "SQL statements completed by operation and outcome.",
            ("operation", "outcome"),
        ),
        db_query_duration_seconds=Histogram(
            "todo_api_db_query_duration_seconds",
            "SQL statement execution duration.",
            ("operation",),
            buckets=DB_DURATION_BUCKETS,
        ),
        db_queries_in_progress=Gauge(
            "todo_api_db_queries_in_progress",
            "SQL statements currently executing.",
            ("operation",),
            multiprocess_mode="livesum",
        ),
        db_pool_events_total=Counter(
            "todo_api_db_pool_events_total",
            "SQLAlchemy connection-pool lifecycle events.",
            ("event",),
        ),
        db_pool_connections=Gauge(
            "todo_api_db_pool_connections",
            "Current application-side database connections by state.",
            ("state",),
            multiprocess_mode="livesum",
        ),
        db_pool_timeouts_total=Counter(
            "todo_api_db_pool_timeouts_total",
            "Times a request could not obtain a pooled connection in time.",
        ),
        auth_attempts_total=Counter(
            "todo_api_auth_attempts_total",
            "Authentication attempts by mechanism and outcome.",
            ("mechanism", "outcome"),
        ),
        user_registrations_total=Counter(
            "todo_api_user_registrations_total",
            "User registration attempts by outcome.",
            ("outcome",),
        ),
    )

    for operation in ("SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "DDL", "OTHER"):
        app_metrics.db_query_duration_seconds.labels(operation=operation)
        app_metrics.db_queries_in_progress.labels(operation=operation)
        for outcome in ("success", "error"):
            app_metrics.db_queries_total.labels(operation=operation, outcome=outcome)

    return app_metrics


metrics = create_metrics()


def configure_build_info(*, version: str, environment: str) -> None:
    metrics.build_info.info({"version": version, "environment": environment})


def record_auth_attempt(mechanism: str, outcome: str) -> None:
    metrics.auth_attempts_total.labels(mechanism=mechanism, outcome=outcome).inc()


def record_registration(outcome: str) -> None:
    metrics.user_registrations_total.labels(outcome=outcome).inc()


def exposition_registry() -> CollectorRegistry:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    return REGISTRY


async def metrics_endpoint() -> Response:
    payload = generate_latest(exposition_registry())
    return Response(
        content=payload,
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )
