# Todo API

An asynchronous FastAPI and PostgreSQL service featuring:

* stateless, short-lived JWT access tokens;
* rotating refresh-token sessions with replay detection;
* sliding refresh expiration and a fixed session lifetime;
* Argon2 password hashing and hashed API keys;
* owner-scoped Todo CRUD, filtering, sorting, and pagination;
* Alembic migrations and Prometheus metrics.

## Run locally

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and PostgreSQL.

```bash
uv sync --group dev
cp .env.example .env
uv run alembic upgrade head
uv run todo-api
```

* OpenAPI: `http://localhost:8000/docs`
* Metrics: `http://localhost:8000/metrics`

## Authentication

Register and log in through:

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
```

Login uses an OAuth2 password form where `username` contains the user's email.

A successful login creates an independent session and returns:

```json
{
  "access_token": "<access-token>",
  "refresh_token": "<refresh-token>",
  "token_type": "bearer",
  "expires_in": 900
}
```

Use the access token for protected endpoints:

```http
Authorization: Bearer <access-token>
```

Rotate or revoke a session by sending its latest refresh token:

```text
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
```

Refresh rotation replaces both tokens. Reusing an old token outside the configured grace period revokes that session.

Access tokens remain valid until expiration because bearer authentication does not query the refresh-session table on every request.

API keys are managed through `/api/v1/api-keys` and used through:

```http
X-API-Key: <api-key>
```

Prefer headers over query-string credentials because URLs may be logged or cached.

## Todos

Bearer-authenticated users can manage their own Todos:

```text
POST   /api/v1/todos
GET    /api/v1/todos
GET    /api/v1/todos/{todo_id}
PATCH  /api/v1/todos/{todo_id}
DELETE /api/v1/todos/{todo_id}
```

Todo lists support search, status, priority, archive and due-date filters, sorting, limit, and offset.

All queries are scoped to the authenticated user. Missing or foreign Todo IDs return `404`.

## Development

```bash
uv run pytest
uv run black --check src tests scripts alembic
uv run ruff check .
uv run mypy src
```

See:

* [API](docs/api.md)
* [Architecture](docs/architecture.md)
* [Database](docs/database.md)
