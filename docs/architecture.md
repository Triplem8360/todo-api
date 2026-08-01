# Architecture

The project uses a small layered architecture:

```text
API routes -> dependencies -> services -> repositories -> models -> PostgreSQL
                                |
                                +-> core security and domain errors
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

## API keys

API keys are intended for machine clients.

The raw key is returned only once. Only its SHA-256 hash is stored.

Prefer the `X-API-Key` header over query-string credentials.
