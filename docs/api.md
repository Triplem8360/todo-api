# API

All paths below use the `/api/v1` prefix.

| Method | Path                      | Authentication            | Purpose                             |
| ------ | ------------------------- | ------------------------- | ----------------------------------- |
| GET    | `/health`                 | None                      | Liveness check                      |
| POST   | `/auth/register`          | None                      | Register a user                     |
| POST   | `/auth/login`             | OAuth2 password form      | Create an independent login session |
| POST   | `/auth/refresh`           | Refresh token in JSON     | Rotate the session token pair       |
| POST   | `/auth/logout`            | Refresh token in JSON     | Revoke a login session              |
| POST   | `/api-keys`               | Bearer access token       | Create an API key                   |
| GET    | `/api-keys`               | Bearer access token       | List owned API keys                 |
| DELETE | `/api-keys/{id}`          | Bearer access token       | Revoke an owned API key             |
| GET    | `/users/me`               | Bearer access token       | Read the current profile            |
| PATCH  | `/users/me`               | Bearer access token       | Update the current profile name     |
| DELETE | `/users/me`               | Bearer access token       | Deactivate the current account      |
| GET    | `/users/me/api-key`       | `X-API-Key` header        | Validate a header API key           |
| GET    | `/users/me/basic`         | HTTP Basic                | Validate email/password credentials |
| GET    | `/users/me/query-api-key` | `api_key` query parameter | Legacy API-key compatibility        |
| POST   | `/todos`                  | Bearer access token       | Create a Todo                       |
| GET    | `/todos`                  | Bearer access token       | List owned Todos                    |
| GET    | `/todos/{todo_id}`        | Bearer access token       | Read an owned Todo                  |
| PATCH  | `/todos/{todo_id}`        | Bearer access token       | Update an owned Todo                |
| DELETE | `/todos/{todo_id}`        | Bearer access token       | Delete an owned Todo                |

## Access and refresh tokens

A successful login or token refresh returns:

```json
{
  "access_token": "<access-token>",
  "refresh_token": "<refresh-token>",
  "token_type": "bearer",
  "expires_in": 900
}
```

`expires_in` contains the actual access-token lifetime in seconds.

It normally matches `access_token_expire_minutes`, but it may be shorter when the login
session is close to its fixed absolute expiration.

## Access tokens

Access tokens are short-lived JWT credentials used for ordinary protected requests:

```http
Authorization: Bearer <access-token>
```

The API validates the access token's:

* signature;
* expiration;
* issuer;
* audience;
* token type;
* required claims.

Access tokens are designed to remain stateless with respect to refresh sessions. Ordinary
bearer authentication does not query the `refresh_sessions` table to determine whether the
corresponding refresh session has been revoked.

Consequently, revoking a refresh session does not retroactively invalidate access tokens
that were already issued by that session.

An existing access token remains usable until its own `exp` claim is reached. The maximum
remaining authorization window after logout, account-session revocation, or refresh-token
replay is therefore bounded by the configured access-token lifetime.

For example:

```text
T+00: access token A2 and refresh token R2 are issued
T+10: an older refresh token is replayed and the login session is revoked
T+10: A2 may still be accepted
T+15: A2 expires and can no longer be used
```

This is an intentional tradeoff:

```text
Benefit:
- no refresh-session database lookup for every bearer request;
- reduced authentication latency;
- lower database load;
- easier horizontal scaling of access-token verification.

Cost:
- session revocation affects future refreshes immediately;
- already-issued access tokens remain valid until expiration.
```

Operations requiring a smaller revocation window should use a shorter configured access-token
lifetime.

## Refresh tokens

Refresh tokens are longer-lived, rotating session credentials.

They must not be used as bearer credentials for ordinary protected endpoints.

Each refresh token contains a session identifier through its `sid` claim. Only a SHA-256
hash of the currently valid refresh token is stored in the database.

The normal refresh-token lifetime is controlled by:

```text
refresh_token_expire_days
```

This lifetime acts as a sliding inactivity limit. A successful refresh issues a new refresh
token with a new expiration.

The login session also has a fixed maximum lifetime controlled by:

```text
refresh_session_absolute_ttl
```

The absolute deadline is created once at login and is never extended by rotation.

The effective lifetimes are:

```text
access-token lifetime =
    minimum of:
    - configured access-token lifetime
    - time remaining before absolute session expiration

refresh-token lifetime =
    minimum of:
    - configured refresh-token lifetime
    - time remaining before absolute session expiration
```

For example, with:

```text
access-token lifetime:     15 minutes
refresh-token lifetime:    30 days
absolute session lifetime: 90 days
```

the effective behavior is:

```text
Immediately after login:
- access token: up to 15 minutes
- refresh token: up to 30 days
- session: up to 90 days

At day 80:
- access token: up to 15 minutes
- refresh token: up to 10 days
- session: 10 days remaining

Five minutes before absolute expiration:
- access token: up to 5 minutes
- refresh token: up to 5 minutes
- session: 5 minutes remaining
```

## Login sessions

Every successful login creates a new independent refresh session.

The API does not reject a login because the user already has another active session, and it
does not replace or revoke older sessions during login.

This allows one account to remain logged in on multiple devices, applications, or browsers.

Each login session has its own:

* session identifier;
* current refresh-token hash;
* previous refresh-token hash;
* sliding inactivity expiration;
* fixed absolute expiration;
* last-use timestamp;
* last-rotation timestamp;
* revocation timestamp.

Revoking one login session does not revoke the user's other login sessions.

## Refresh-token rotation

When an access token expires or is close to expiration, send the latest refresh token to:

```http
POST /api/v1/auth/refresh
Content-Type: application/json
```

```json
{
  "refresh_token": "<latest-refresh-token>"
}
```

The server:

1. validates the refresh-token JWT;
2. extracts its user and session identifiers;
3. locks the corresponding refresh-session row;
4. confirms that the row belongs to the token subject;
5. checks inactivity, absolute expiration, and revocation state;
6. compares the presented token hash with the stored hash;
7. confirms that the user exists and is active;
8. issues a new access token and refresh token;
9. replaces the current stored refresh-token hash;
10. retains the previous token hash temporarily for race detection;
11. updates the rotation and last-use timestamps;
12. commits the rotation in one transaction.

The login-session identifier remains unchanged during rotation.

Clients must replace both tokens after every successful refresh:

```text
old access token  -> discard
old refresh token -> discard
new access token  -> store
new refresh token -> store
```

## Concurrent refresh requests

Clients should serialize refresh operations so that only one refresh request is active at
a time.

For example, multiple browser tabs or simultaneous failed API requests should share the
same in-progress refresh operation rather than independently submitting the same refresh
token.

The server retains the immediately previous refresh-token hash for a short period controlled
by:

```text
refresh_token_reuse_grace
```

This grace period prevents a near-simultaneous duplicate from automatically being classified
as credential theft.

It is intended to handle conditions such as:

* concurrent refresh requests;
* an interrupted refresh response;
* an immediate network retry;
* multiple client requests reacting to the same expired access token.

The grace mechanism does not replace client-side refresh serialization. The old token must
still be discarded after a successful rotation.

## Refresh-token replay

Presenting an older refresh token outside the permitted recovery window is treated as
possible credential theft.

When replay is detected, the affected refresh session is revoked.

Revocation immediately prevents that session from obtaining additional access or refresh
tokens. It does not invalidate access tokens that have already been issued because access
tokens are verified without a refresh-session database lookup.

Other independent login sessions belonging to the same user remain active.

After replay detection, the affected client must authenticate again after its current access
token expires or after it otherwise clears its local authentication state.

## Logout

Send a refresh token belonging to the session that should be revoked:

```http
POST /api/v1/auth/logout
Content-Type: application/json
```

```json
{
  "refresh_token": "<refresh-token>"
}
```

Logout revokes the identified refresh session and prevents it from rotating or issuing
additional token pairs.

Logout is idempotent. Invalid, unknown, expired, or already revoked refresh tokens do not
produce an authentication error.

A successful logout returns:

```http
204 No Content
```

Because access tokens are stateless with respect to refresh-session revocation, an access
token issued before logout may remain usable until its own expiration.

Clients should therefore delete both the access token and refresh token immediately after
calling logout.

## Client requirements

Clients should:

* store refresh tokens in secure platform-appropriate storage;
* replace access and refresh tokens together after rotation;
* serialize refresh operations;
* use only the most recently returned refresh token;
* avoid refreshing continuously while the application is idle;
* clear both tokens after logout;
* clear authentication state after an invalid, expired, or revoked refresh session;
* never send refresh tokens as ordinary bearer credentials.

## Todos

Todo endpoints require a bearer access token:

```http
Authorization: Bearer <access-token>
```

All operations are scoped to the authenticated user. A missing Todo or a Todo owned by
another user returns `404 Not Found`.

### Create

```http
POST /api/v1/todos
Content-Type: application/json
```

```json
{
  "title": "Finish documentation",
  "description": "Document the Todo endpoints",
  "priority": "high",
  "due_at": "2026-08-01T12:00:00Z"
}
```

A successful request returns `201 Created` with the created Todo.

### List

```http
GET /api/v1/todos
```

Supported query parameters:

* `q`;
* `status`;
* `priority`;
* `is_archived`;
* `due_from` and `due_to`;
* `sort_by`;
* `sort_direction`;
* `limit` and `offset`.

Supported sort fields are `created_at`, `updated_at`, `due_at`, and `title`.
Sort direction may be `asc` or `desc`.

Example:

```http
GET /api/v1/todos?status=pending&priority=high&sort_by=due_at&sort_direction=asc
```

The response contains:

```json
{
  "items": [],
  "total": 0,
  "limit": 20,
  "offset": 0
}
```

### Read

```http
GET /api/v1/todos/{todo_id}
```

The Todo ID must be a positive integer.

### Update

```http
PATCH /api/v1/todos/{todo_id}
Content-Type: application/json
```

```json
{
  "status": "completed",
  "priority": "medium",
  "is_archived": false
}
```

Only provided fields are updated. Supported fields are:

* `title`;
* `description`;
* `status`;
* `priority`;
* `due_at`;
* `is_archived`.

The service manages `completed_at` according to the Todo status.

### Delete

```http
DELETE /api/v1/todos/{todo_id}
```

A successful deletion returns `204 No Content`.

### Todo errors

Todo operations may return:

| Status | Meaning                         |
| ------ | ------------------------------- |
| `401`  | Invalid or missing access token |
| `403`  | Inactive authenticated user     |
| `404`  | Todo not found                  |
| `409`  | Invalid Todo state change       |
| `422`  | Request validation failed       |
| `503`  | Todo service temporarily failed |

Create, update, and delete operations are committed atomically. Database errors are rolled
back and converted into stable application errors.

## Other authentication methods

Bearer access tokens are the primary user-authentication mechanism.

API keys are intended for machine clients. Prefer:

```http
X-API-Key: <api-key>
```

over query-string credentials.

Basic authentication and query-string API keys remain available for compatibility. Query
parameters are less secure because URLs can be retained in logs, caches, browser history,
analytics systems, and proxy records.

## Error responses

Application errors use a stable response shape:

```json
{
  "detail": "Human-readable message.",
  "code": "machine_readable_code"
}
```

### Common authentication responses

| Status | Meaning                                        |
| ------ | ---------------------------------------------- |
| `401`  | Missing, invalid, or expired credentials       |
| `403`  | The authenticated user is inactive             |
| `409`  | Authentication state conflict                  |
| `503`  | Authentication service temporarily unavailable |
