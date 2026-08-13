# Architecture

The project uses a small layered architecture:

```text
API routes -> dependencies -> services -> repositories -> models -> PostgreSQL
    |                           |
    |                           +-> core security and domain errors
    +-> per-user Todo read cache
```

* Routes handle HTTP input, responses, error mapping, and metrics.
* Dependencies provide database sessions, settings, authenticated users, and request-scoped services.
* Services enforce business rules, commit successful writes, and raise domain errors.
* Repositories contain reusable and owner-scoped database queries.
* Models define persisted entities and relationships.
* The database-session dependency rolls back transactions when request processing raises an exception.
* Core security creates, validates, and hashes tokens and credentials.
* Domain errors keep service failures independent from HTTP responses.

## Authentication lifecycle

### Authorization Code + PKCE

The OpenAPI security scheme describes an OAuth 2.0 Authorization Code flow. The application
currently acts as both authorization server and resource server for one configured first-party
public client. Swagger UI is the built-in development client, not part of the server-side
security boundary.

```text
Swagger UI or another client
    |
    | GET /auth/authorize + state + S256 challenge
    v
authorization route -> OAuthService -> AuthService -> user repository
    |
    | 303 redirect + plaintext one-time code
    v
client callback
    |
    | POST /auth/token + code + original verifier
    v
token route -> OAuthService -> OAuth repository -> AuthService
    |
    | access token + rotating refresh token
    v
protected API route -> access-token dependency -> owner-scoped repository
```

The client owns the transient protocol values. It generates and retains the PKCE verifier,
derives its S256 challenge, generates `state`, validates the returned state, follows the
callback, and performs the token request. The server does not persist `state`; it validates
the authorization request and returns state unchanged.

The server authenticates the resource owner at the authorization endpoint. After successful
password authentication, `OAuthService` generates a plaintext one-time code and passes its
SHA-256 hash and immutable user, client, redirect, challenge, and expiry bindings to the OAuth
repository. The plaintext code exists only in the redirect response.

The token exchange calculates the S256 challenge from the presented verifier. The repository
uses one `UPDATE ... RETURNING` statement constrained by every binding, the expiration
predicate, and `consumed_at IS NULL`. A successful match records consumption while retaining
the row for lifecycle visibility and replay rejection.

Authorization-code consumption and refresh-session creation use the same database session and
commit. A propagated persistence error rolls back both, so the code is not lost without a token
pair and a token pair is not committed without consuming the code.

No OAuth scopes currently participate in this lifecycle. Non-empty scope requests are rejected,
access tokens have no scope claim, and protected resources rely on the token subject, active-user
validation, and ownership queries. A future scope implementation must carry one non-escalating
authorized scope set across the authorization code, access token, and refresh session.

### Login

Login verifies the user's password and creates a new independent refresh session.

Multiple sessions are allowed for the same user. Logging in from one device does not replace
or revoke sessions on other devices.

The server returns:

* a short-lived access token;
* a rotating refresh token;
* the access-token lifetime in seconds.

### Access tokens

Access tokens are signed JWTs used for protected requests:

```http
Authorization: Bearer <access_token>
```

They are validated without querying the refresh-session table on every request. This keeps
access-token authentication stateless and reduces database load.

Revoking a refresh session prevents future refreshes but does not invalidate access tokens
already issued from that session. Those tokens remain valid until expiration.

### Refresh tokens

Refresh tokens are stateful, rotating credentials.

Each token contains a session identifier in its `sid` claim. Only its SHA-256 hash is stored.

During refresh, the service:

1. validates the token;
2. locks the session row;
3. checks ownership, expiration, revocation, and token hashes;
4. verifies that the user is active;
5. issues and stores the new token pair;
6. updates session timestamps;
7. commits the transaction.

The session identifier remains unchanged during rotation.

### Browser cookie transport

The browser-session routes reuse the same token issuance, refresh-session persistence, token
rotation, replay detection, and revocation services. The transport layer stores access and
refresh JWTs in scoped HttpOnly cookies instead of exposing them in JSON.

A separate readable CSRF cookie implements the double-submit pattern. When an access cookie is
selected because no explicit bearer credential was supplied, unsafe request methods require a
matching `X-CSRF-Token` header. Header-based bearer authentication remains independent of CSRF
because browsers do not attach authorization headers ambiently.

The refresh cookie is scoped to the browser-auth route subtree, while access and CSRF cookies
are scoped to the versioned API. Cookie Max-Age values are derived from the issued token
lifetimes, including the fixed session deadline. Login and refresh responses use `no-store`,
and refresh rotates the CSRF value together with both credentials.

### Token lifetime

Authentication uses:

```text
access_token_expire_minutes
refresh_token_expire_days
refresh_session_absolute_ttl
```

The refresh-token lifetime is sliding, while the absolute session lifetime is fixed at
login.

New access and refresh tokens cannot expire after the absolute session deadline.

### Replay detection

The current and immediately previous refresh-token hashes are retained.

A previous token may be accepted during a short recovery window for concurrent requests.
Older or out-of-window reuse is treated as possible credential theft and revokes the affected
session.

### Logout

Logout revokes only the session represented by the submitted refresh token.

The operation is idempotent. Invalid, expired, unknown, or already revoked tokens still
produce a successful response.

## Todo lifecycle

Todo routes receive the authenticated user and a request-scoped Todo service through
dependencies.

The service:

1. enforces Todo business rules;
2. calls owner-scoped repository queries;
3. commits successful write operations;
4. converts persistence failures into domain errors.

The database-session dependency provides the shared rollback boundary. Any exception that
propagates through the request causes the active session transaction to be rolled back.

Every read, update, and delete query includes the authenticated user's ID.

A Todo owned by another user is therefore returned as not found, preventing resource
enumeration.

Todo state rules, including completion timestamp handling, belong to the service layer rather
than routes or database models.

### Todo read cache

`GET /todos` and `GET /todos/{todo_id}` use `fastapi-cache2` with Redis by default.
Authentication and request dependencies still execute on every request. A cache hit skips the
Todo service and its owner-scoped Todo queries; it does not skip access-token or active-user
validation.

Each key contains the cache namespace, authenticated user ID, endpoint identity, and a SHA-256
digest of the normalized list query or Todo ID. Tokens, cookies, database sessions, and service
objects are deliberately excluded. This keeps keys stable across requests and prevents values
from being shared between users.

Successful create, update, and delete operations clear the complete Todo namespace for the
affected user after the database commit. Invalidation is best-effort because a cache failure
must not turn an already-committed write into an error response; the configured TTL bounds any
remaining stale value.

The application registers the selected backend during its lifespan and closes owned resources
on shutdown. `CACHE_ENABLED` controls whether decorators use it, `CACHE_BACKEND` selects
`redis` or `memory`, `CACHE_PREFIX` identifies application-owned entries, and
`CACHE_TTL_SECONDS` controls entry lifetime. The default TTL is 60 seconds and validation
permits values from 1 through 3600 seconds. `REDIS_URL` identifies the Redis database; connect
and socket timeouts are both configurable so a cache outage cannot hold requests indefinitely.

The endpoint `@cache` decorator is deliberately backend-neutral. The backend is a process-wide
`fastapi-cache2` registration, so changing `CACHE_BACKEND` switches both cached Todo endpoints
without changing their route code. The route comments make the original memory option visible
where the decorators are applied.

Cached HTTP responses use `Cache-Control: private, no-store`. Browser and shared proxy caches
therefore do not retain authenticated Todo data, while `X-FastAPI-Cache` reports the server-side
`MISS` or `HIT`. Credential-based `Vary` headers provide additional protection.

Redis keeps encoded response values and expiry metadata outside the API processes. All workers
therefore observe the same keys, hits, and per-user invalidations. Redis entries are not deleted
when one API worker shuts down, because other workers may still use them; the worker only closes
its Redis connection pool. Cache read and write failures degrade to database reads, and
post-commit invalidation remains best-effort.

The original `InMemoryBackend` remains available with `CACHE_BACKEND=memory`. It avoids an
external dependency and is useful in unit tests or a single-worker local environment. Every
worker has an independent memory cache, however, so cross-worker invalidation is not possible.
Both Compose definitions supply an ephemeral Redis cache at `redis://redis:6379/0` and publish it
only on host loopback for direct host execution. They disable Redis persistence, limit cache
memory to `REDIS_MAX_MEMORY` (`128mb` by default), and use `allkeys-lru` eviction when the limit
is reached. Externally managed deployments continue to supply their own reachable `REDIS_URL`.

## API keys

API keys are intended for machine clients.

The raw key is returned only once. Only its SHA-256 hash is stored.

Prefer the `X-API-Key` header over query-string credentials.
