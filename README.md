# Todo API

An asynchronous FastAPI service demonstrating production-oriented authentication with PostgreSQL:

* short-lived, stateless JWT access tokens;
* rotating and independently revocable refresh-token sessions;
* sliding refresh-token expiration with a fixed absolute session lifetime;
* refresh-token replay detection;
* Argon2 password hashing;
* hashed API keys for machine access;
* Alembic migrations;
* Prometheus metrics.

## Run locally

Requirements:

* Python 3.11+
* [uv](https://docs.astral.sh/uv/)
* PostgreSQL

```bash
uv sync --group dev
cp .env.example .env
uv run alembic upgrade head
uv run todo-api
```

OpenAPI documentation is available at:

```text
http://localhost:8000/docs
```

Prometheus metrics are exposed at:

```text
/metrics
```

## Authentication flow

Register a user, then submit the email through OAuth2's `username` form field:

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "user@example.com",
    "password": "strong-pass-123",
    "full_name": "Example User"
  }'
```

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=user@example.com&password=strong-pass-123'
```

Every successful login creates a new independent login session. Existing sessions for the
same user are not replaced or revoked, allowing the account to remain signed in on multiple
devices or browsers.

A successful login returns an access token and a refresh token:

```json
{
  "access_token": "<access-token>",
  "refresh_token": "<refresh-token>",
  "token_type": "bearer",
  "expires_in": 900
}
```

Use the access token for protected user operations:

```http
Authorization: Bearer <access-token>
```

For example:

```bash
curl http://localhost:8000/api/v1/users/me \
  -H 'Authorization: Bearer <access-token>'
```

When the access token expires, send the latest refresh token to:

```text
POST /api/v1/auth/refresh
```

```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh-token>"}'
```

A successful refresh rotates the token pair. Replace both locally stored tokens with the
new values returned by the API.

Send the latest refresh token to the logout endpoint to revoke that login session:

```bash
curl -X POST http://localhost:8000/api/v1/auth/logout \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh-token>"}'
```

Refresh-session revocation prevents the session from issuing additional token pairs.
Already-issued access tokens remain valid until their own expiration because bearer
authentication does not perform a refresh-session database lookup on every request.

This is an intentional tradeoff that preserves the stateless advantages of short-lived JWT
access tokens. The maximum remaining authorization window after logout or refresh-token
replay is therefore bounded by the access-token lifetime.

Bearer-authenticated users can manage API keys through:

```text
/api/v1/api-keys
```

API keys authenticate machine clients through the `X-API-Key` header. For example:

```text
GET /api/v1/users/me/api-key
```

Prefer the `X-API-Key` header over query-string API keys because URLs may be retained in
logs, caches, analytics systems, proxies, and browser history.

## Token lifetimes

The authentication system uses three related lifetime settings:

* `access_token_expire_minutes`: normal access-token lifetime;
* `refresh_token_expire_days`: sliding refresh-token inactivity lifetime;
* `refresh_session_absolute_ttl`: maximum total lifetime of a login session.

Token lifetimes are bounded by the fixed absolute session deadline. Near the end of a
session, newly issued access and refresh tokens may therefore have shorter lifetimes than
their normal configured values.

Refresh-token rotation never extends the session beyond its original absolute expiration.

## Development

Run the test suite:

```bash
uv run pytest
```

Check formatting:

```bash
uv run black --check src tests scripts alembic
```

See:

* [API notes](docs/api.md)
* [Architecture](docs/architecture.md)
* [Database design](docs/database.md)
