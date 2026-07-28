from __future__ import annotations

from time import perf_counter
from typing import Any
from weakref import WeakSet

from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine, ExceptionContext
from sqlalchemy.ext.asyncio import AsyncEngine

from todo_api.observability.metrics import AppMetrics

_instrumented_engines: WeakSet[Engine] = WeakSet()
_KNOWN_OPERATIONS = {"SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "DDL"}


def _operation(statement: str, context: Any) -> str:
    compiled_statement = getattr(getattr(context, "compiled", None), "statement", None)
    visit_name = str(getattr(compiled_statement, "__visit_name__", "")).upper()
    if visit_name in _KNOWN_OPERATIONS:
        return visit_name

    first_word = statement.lstrip().split(maxsplit=1)[0].upper() if statement.strip() else ""
    if first_word in _KNOWN_OPERATIONS:
        return first_word
    if first_word in {"CREATE", "ALTER", "DROP", "TRUNCATE"}:
        return "DDL"
    return "OTHER"


def install_database_metrics(engine: AsyncEngine, metrics: AppMetrics) -> None:
    sync_engine = engine.sync_engine
    if sync_engine in _instrumented_engines:
        return
    _instrumented_engines.add(sync_engine)

    @event.listens_for(sync_engine, "before_cursor_execute")
    def before_cursor_execute(
        connection: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        del cursor, parameters, executemany
        operation = _operation(statement, context)
        connection.info.setdefault("todo_api_query_timers", []).append((perf_counter(), operation))
        metrics.db_queries_in_progress.labels(operation=operation).inc()

    @event.listens_for(sync_engine, "after_cursor_execute")
    def after_cursor_execute(
        connection: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        del cursor, statement, parameters, context, executemany
        timers = connection.info.get("todo_api_query_timers", [])
        if not timers:
            return
        started_at, operation = timers.pop()
        metrics.db_queries_in_progress.labels(operation=operation).dec()
        metrics.db_queries_total.labels(operation=operation, outcome="success").inc()
        metrics.db_query_duration_seconds.labels(operation=operation).observe(
            perf_counter() - started_at
        )

    @event.listens_for(sync_engine, "handle_error")
    def handle_error(exception_context: ExceptionContext) -> None:
        connection = exception_context.connection
        if connection is None:
            return
        timers = connection.info.get("todo_api_query_timers", [])
        if not timers:
            return
        started_at, operation = timers.pop()
        metrics.db_queries_in_progress.labels(operation=operation).dec()
        metrics.db_queries_total.labels(operation=operation, outcome="error").inc()
        metrics.db_query_duration_seconds.labels(operation=operation).observe(
            perf_counter() - started_at
        )

    pool = sync_engine.pool

    @event.listens_for(pool, "connect")
    def connect(dbapi_connection: Any, connection_record: Any) -> None:
        del dbapi_connection, connection_record
        metrics.db_pool_events_total.labels(event="connect").inc()
        metrics.db_pool_connections.labels(state="open").inc()

    @event.listens_for(pool, "close")
    def close(dbapi_connection: Any, connection_record: Any) -> None:
        del dbapi_connection, connection_record
        metrics.db_pool_events_total.labels(event="close").inc()
        metrics.db_pool_connections.labels(state="open").dec()

    @event.listens_for(pool, "checkout")
    def checkout(
        dbapi_connection: Any,
        connection_record: Any,
        connection_proxy: Any,
    ) -> None:
        del dbapi_connection, connection_record, connection_proxy
        metrics.db_pool_events_total.labels(event="checkout").inc()
        metrics.db_pool_connections.labels(state="checked_out").inc()

    @event.listens_for(pool, "checkin")
    def checkin(dbapi_connection: Any, connection_record: Any) -> None:
        del dbapi_connection, connection_record
        metrics.db_pool_events_total.labels(event="checkin").inc()
        metrics.db_pool_connections.labels(state="checked_out").dec()

    @event.listens_for(pool, "invalidate")
    def invalidate(
        dbapi_connection: Any,
        connection_record: Any,
        exception: BaseException | None,
    ) -> None:
        del dbapi_connection, connection_record, exception
        metrics.db_pool_events_total.labels(event="invalidate").inc()
