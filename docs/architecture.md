# Architecture

The project uses a small layered architecture:

```text
API routes -> dependencies/services -> repositories -> models -> PostgreSQL
                    |
                    +-> security utilities and domain errors
```

* Routes handle HTTP input, output, and metrics.
* Dependencies resolve authenticated identities.
* Services contain authentication rules and transaction boundaries.
* Repositories contain reusable database queries.
* Models define persisted entities and state transitions.
* Core security creates, validates, and hashes tokens and credentials.

## Authentication lifecycle

### Login

Login verifies the user's password and creates a new independent refresh session.

Multiple login sessions are allowed for the same user. Logging in from one device does not
replace or revoke sessions from other devices.

The server returns:

* a short-lived access token;
* a rotating refresh token;
* the access-token lifetime in seconds.

### Access tokens

Access tokens are signed JWTs used for protected requests:

```http
Authorization: Bearer <access_token>
```

They are validated without checking the refresh-session table on every request. This keeps
access-token authentication stateless and reduces database load.

Revoking a refresh session therefore does not immediately invalidate access tokens already
issued from that session. Those tokens remain usable until their own expiration.

The access-token lifetime limits this revocation window.

### Refresh tokens

Refresh tokens are stateful, rotating credentials.

Each refresh token contains a session identifier in its `sid` claim. Only its SHA-256 hash
is stored in the database.

During refresh, the service:

1. validates the token;
2. locks the related session row;
3. checks ownership, expiration, revocation, and token hash;
4. verifies that the user is active;
5. issues a new access and refresh token;
6. rotates the stored refresh-token hash;
7. commits the transaction.

The session identifier remains unchanged during rotation.

### Token lifetime

Authentication uses three limits:

```text
access_token_expire_minutes
refresh_token_expire_days
refresh_session_absolute_ttl
```

The refresh-token lifetime is sliding and can be extended by successful rotation.

The absolute session lifetime is fixed at login and is never extended.

New access and refresh tokens cannot expire later than the absolute session deadline.

### Replay detection

The current and immediately previous refresh-token hashes are retained.

A previous token may be recognized during a short recovery window for near-simultaneous
requests. Older or out-of-window token reuse is treated as possible credential theft and
revokes that refresh session.

Revocation prevents future refreshes but does not invalidate already-issued access tokens.

### Logout

Logout revokes only the session represented by the submitted refresh token.

The operation is idempotent. Invalid, expired, unknown, or already revoked tokens still
produce a successful logout response.

## API keys

API keys are intended for machine clients.

The raw key is returned only once. Only its SHA-256 hash is stored.

Prefer the `X-API-Key` header over query-string API keys.
