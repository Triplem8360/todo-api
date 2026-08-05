from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from starlette.responses import JSONResponse

from todo_api import __version__
from todo_api.api.exception_handlers import register_exception_handlers
from todo_api.api.v1.router import api_router
from todo_api.core.config import Settings, get_settings
from todo_api.core.cors import register_cors_middleware
from todo_api.db.session import Database, create_database
from todo_api.observability.database import install_database_metrics
from todo_api.observability.metrics import (
    configure_build_info,
    metrics,
    metrics_endpoint,
)
from todo_api.observability.middleware import HTTPMetricsMiddleware
from todo_api.observability.request_context import RequestContextMiddleware


def create_app(
    app_settings: Settings | None = None,
    database: Database | None = None,
) -> FastAPI:
    settings = app_settings or get_settings()
    db = database or create_database(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await db.ping(settings.db_healthcheck_timeout_seconds)

        try:
            yield
        finally:
            await db.dispose()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        version=__version__,
        lifespan=lifespan,
        swagger_ui_init_oauth={
            "clientId": settings.oauth2_public_client_id,
            "appName": f"{settings.app_name} Swagger UI",
            "usePkceWithAuthorizationCodeGrant": True,
            "useBasicAuthenticationWithAccessCodeGrant": False,
        },
    )

    app.state.settings = settings
    app.state.database = db
    app.state.metrics = metrics

    configure_build_info(version=__version__, environment=settings.app_env)
    install_database_metrics(db.engine, metrics)

    # Starlette executes user middleware in reverse registration order.
    #
    # Effective request order:
    #
    # TrustedHostMiddleware
    #   -> CORSMiddleware
    #       -> RequestContextMiddleware
    #           -> HTTPMetricsMiddleware
    #               -> FastAPI
    app.add_middleware(
        HTTPMetricsMiddleware,
        metrics=metrics,
        metrics_path=settings.metrics_path,
    )
    app.add_middleware(RequestContextMiddleware)
    register_cors_middleware(app, settings=settings)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(settings.allowed_hosts),
        www_redirect=False,
    )

    app.add_api_route(
        settings.metrics_path,
        metrics_endpoint,
        methods=["GET"],
        include_in_schema=False,
    )
    app.include_router(api_router)

    @app.exception_handler(SQLAlchemyTimeoutError)
    async def database_pool_timeout_handler(
        request: Request, exc: SQLAlchemyTimeoutError
    ) -> JSONResponse:
        del request, exc

        metrics.db_pool_timeouts_total.inc()

        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "Database capacity is temporarily unavailable.",
                "code": "database_capacity_unavailable",
            },
        )

    register_exception_handlers(app)

    return app
