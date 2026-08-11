# syntax=docker/dockerfile:1.7

FROM python:3.11-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=/app/uv.lock,readonly \
    --mount=type=bind,source=pyproject.toml,target=/app/pyproject.toml,readonly \
    --mount=type=bind,source=README.md,target=/app/README.md,readonly \
    uv sync \
        --locked \
        --no-dev \
        --no-install-project

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
        --locked \
        --no-dev \
        --no-editable


FROM python:3.11-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd \
        --system \
        --gid 10001 \
        app \
    && useradd \
        --system \
        --uid 10001 \
        --gid app \
        --home-dir /app \
        --no-create-home \
        --shell /usr/sbin/nologin \
        app

WORKDIR /app

COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --chown=app:app alembic.ini ./alembic.ini
COPY --chown=app:app alembic ./alembic

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).read()"]

CMD ["uvicorn", "todo_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
