# Todo API

An asynchronous FastAPI and PostgreSQL service featuring:

* stateless, short-lived JWT access tokens;
* OAuth 2.0 Authorization Code flow with mandatory PKCE/S256;
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
