# Todo API

An asynchronous FastAPI and PostgreSQL service featuring:

* stateless, short-lived JWT access tokens;
* OAuth 2.0 Authorization Code flow with mandatory PKCE/S256;
* rotating refresh-token sessions with replay detection;
* HttpOnly browser sessions with scoped cookies and CSRF protection;
* sliding refresh expiration and a fixed session lifetime;
* Argon2 password hashing and hashed API keys;
* owner-scoped Todo CRUD, filtering, sorting, and pagination;
* per-user Redis caching for Todo reads, with an in-memory option;
* Redis-backed APScheduler maintenance jobs;
* Alembic migrations and Prometheus metrics.

## Run locally

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), PostgreSQL, and a reachable Redis
instance. `CACHE_BACKEND=memory` disables Redis for Todo caching, but the maintenance scheduler
still requires Redis for its shared job store.

```bash
uv sync --group dev
cp .env.example .env
uv run alembic upgrade head
uv run todo-api
```

* OpenAPI: `http://localhost:8000/docs`
* Metrics: `http://localhost:8000/metrics`

## Run with Docker

Requires Docker Engine with the Compose plugin. Create the local environment file once:

```bash
cp .env.example .env
```

The images can be built independently without starting containers:

```bash
docker build --file Dockerfile --tag todo-api:latest .
docker build --file Dockerfile.dev --tag todo-api:dev .
```

The production image contains only runtime dependencies and runs as an unprivileged user. The
development image includes the development dependency group and starts Uvicorn with reload.
Use Compose for a runnable local stack because the API requires PostgreSQL during startup.

Start the production-style image, PostgreSQL, Redis, and the one-shot migration service:

```bash
docker compose up --build
```

Compose waits for PostgreSQL and Redis to become healthy, applies Alembic migrations, and then
starts one API worker at `http://localhost:8000`. Redis is available to containers through the
Compose network and is published only on `127.0.0.1:${REDIS_PORT:-6379}` for host-run API
processes. It is configured as an ephemeral cache with a `128mb` default memory limit and
`allkeys-lru` eviction. Override the limit with `REDIS_MAX_MEMORY`. Run the stack in the
background with `-d` if preferred.

For development with source mounts and Uvicorn reload, combine the base and development files:

```bash
docker compose -f compose.yaml -f compose.dev.yaml up --build
```

The development file can also run by itself. It overrides host-oriented `.env` connection URLs
with the Docker service names `db` and `redis` for the migration and API containers:

```bash
docker compose -f compose.dev.yaml up --build
```

On Linux, set `HOST_UID` and `HOST_GID` before the first development build if the host user is
not UID/GID `1000`. PostgreSQL is also exposed at `localhost:5432` in the development setup.

Useful commands:

```bash
# Follow API logs
docker compose logs -f api

# Apply migrations explicitly
docker compose run --rm migrate

# Run tests in the development image
docker compose -f compose.yaml -f compose.dev.yaml run --rm api pytest

# Stop containers while preserving PostgreSQL data
docker compose down

# Stop containers and delete the PostgreSQL volume
docker compose down --volumes
```

The last command permanently removes the Compose-managed development database. Rebuild the
images after changing `pyproject.toml` or `uv.lock`.

## Authentication and OAuth

Register through `POST /api/v1/auth/register`. The primary interactive flow is OAuth 2.0
Authorization Code with mandatory PKCE/S256:

```text
GET  /api/v1/auth/authorize  -> validate the request and display the sign-in page
POST /api/v1/auth/authorize  -> authenticate the user and issue a one-time code
POST /api/v1/auth/token      -> exchange the code and PKCE verifier for a token pair
```

The service currently supports one configured first-party public client. Public clients do
not have a client secret, so PKCE binds each short-lived authorization code to the client
instance that started the flow. The client must use an exact registered redirect URI and a
fresh verifier for every authorization attempt.

Swagger UI acts as an OAuth client for local development. Clicking its authorization control
causes Swagger UI to:

1. generate a `code_verifier`, its S256 `code_challenge`, and `state`;
2. open `/api/v1/auth/authorize` with the challenge and callback URI;
3. receive the authorization code at `/docs/oauth2-redirect`;
4. call `/api/v1/auth/token` with the code and original verifier;
5. attach the returned access token to protected requests.

The API authenticates the user's email and password, creates and consumes the authorization
code, verifies PKCE, and issues the tokens. Swagger UI is only one client of this protocol;
other browser, mobile, or native clients can perform the same flow.

`state` belongs to the client. The API returns it unchanged, and the client must validate it
against the value associated with the authorization attempt. OAuth scopes are not implemented
yet: an empty `scope` is accepted and every non-empty scope request returns `invalid_scope`.
Protected resources are currently authorized through the authenticated user and resource
ownership.

`POST /api/v1/auth/login` remains available as a separate direct first-party password login.
Either successful login path creates an independent refresh session and returns:

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

### Browser cookie sessions

Browser clients that do not need direct token access can use:

```text
POST /api/v1/auth/browser/login
POST /api/v1/auth/browser/refresh
POST /api/v1/auth/browser/logout
```

Login uses the same OAuth2 password form as `/auth/login`, but returns only session metadata.
The access and refresh tokens are stored in `HttpOnly` cookies, so application JavaScript
cannot read them. A third, readable `todo_csrf_token` cookie must be copied into the
`X-CSRF-Token` header for refresh, logout, and any unsafe cookie-authenticated API request.
Bearer-header clients do not need the CSRF header.

The refresh cookie is restricted to `/api/v1/auth/browser`; the short-lived access and CSRF
cookies are restricted to `/api/v1`. Cookie lifetimes follow the actual JWT/session deadline,
and all three values rotate together on refresh. Configure deployment behavior with:

```env
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=lax
```

`AUTH_COOKIE_SECURE=true` is required by configuration validation in staging and production.

OAuth client settings are configured through:

```env
OAUTH2_PUBLIC_CLIENT_ID=todo-public-client
OAUTH2_REDIRECT_URIS=["http://localhost:8000/docs/oauth2-redirect"]
OAUTH2_AUTHORIZATION_CODE_TTL_SECONDS=120
```

Redirect URI comparison is exact. Register every origin used to open Swagger UI, such as
`localhost` and `127.0.0.1`, as a separate URI.

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

Todo list and detail reads are cached in Redis for 60 seconds by default. Cache keys include the
authenticated user and normalized request inputs, and successful Todo writes clear that user's
cached reads. Because Redis is shared, cache hits and invalidations work across API workers.
Configure the cache with:

```env
CACHE_ENABLED=true
CACHE_BACKEND=redis
CACHE_PREFIX=todo-api
CACHE_TTL_SECONDS=60
REDIS_URL=redis://localhost:6379/0
REDIS_CONNECT_TIMEOUT_SECONDS=2
REDIS_SOCKET_TIMEOUT_SECONDS=2
APSCHEDULER_REDIS_DB=1
APSCHEDULER_JOBS_KEY=todo-api:apscheduler:jobs
APSCHEDULER_RUN_TIMES_KEY=todo-api:apscheduler:run-times
```

Cached responses expose `X-FastAPI-Cache: MISS` or `HIT`. They use
`Cache-Control: private, no-store`, so browsers always contact the API while the server can
reuse the server-side value. If Redis is temporarily unavailable, Todo reads continue through
the database and cache operations are logged as warnings.

The original in-memory backend remains available without endpoint changes:

```env
CACHE_BACKEND=memory
```

Memory is convenient for tests and single-process development, but every worker owns an
independent cache. Redis is the recommended backend for multiple workers. `compose.yaml`
and `compose.dev.yaml` provide matching Redis services and override the container URL with
`redis://redis:6379/0`; direct host execution uses the configured `REDIS_URL` through the
loopback-only published port.

APScheduler reuses the server, credentials, and timeout settings from `REDIS_URL`, overrides the
logical database with `APSCHEDULER_REDIS_DB` (DB 1 by default), and stores jobs and next-run times
under the two configured keys. The scheduler and its maintenance jobs are still created and
started during the FastAPI lifespan. Existing job IDs are replaced at startup, so interval
definitions stay aligned with the running application while their state is shared through Redis.

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
