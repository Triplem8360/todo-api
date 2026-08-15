# Database

PostgreSQL is accessed asynchronously through SQLAlchemy and `asyncpg`.

Alembic manages schema changes:

```bash
uv run alembic upgrade head
```

## Tables

The schema contains:

* `users`;
* `refresh_sessions`;
* `oauth_authorization_codes`;
* `api_keys`;
* `todos`.

## Users

The `users` table stores:

* normalized email;
* Argon2 password hash;
* email-verification timestamp, token hash, expiry, and most recent request time;
* profile fields;
* active and superuser flags;
* timestamps.

The email unique constraint provides uniqueness and an indexed lookup. Verification tokens are
never stored directly: a nullable unique SHA-256 hash supports indexed, single-use lookup. The
verification timestamp is backfilled for accounts that existed before the feature was added.

Deleting a user cascades to their refresh sessions, authorization codes, API keys, and Todos.

## OAuth authorization codes

`oauth_authorization_codes` represents the server-side lifecycle of short-lived Authorization
Code grants. It contains the immutable bindings needed for token exchange and the timestamp of
successful consumption:

* `code_hash`: SHA-256 code hash and primary lookup key;
* `user_id`: resource owner;
* `client_id`: public client binding;
* `redirect_uri`: exact redirect binding;
* `code_challenge`: 43-character S256 PKCE challenge;
* `expires_at`: redemption deadline;
* `consumed_at`: successful one-time redemption timestamp;
* creation and update timestamps.

The raw authorization code is never stored. Its SHA-256 hash is the lookup key, so disclosure
of the table does not directly reveal an exchangeable code. The PKCE verifier is also never
stored; only the challenge derived by the client is persisted.

Successful exchange calculates a challenge from the presented verifier and marks the matching
row with one `UPDATE ... RETURNING` statement. The update includes every client and PKCE binding,
requires an unexpired record, and succeeds only while `consumed_at IS NULL`. Retaining the row
preserves the grant lifecycle and makes subsequent exchange attempts fail as replay.

The code-consumption update and refresh-session insert share one transaction. If session
creation or commit fails, both changes roll back.

`state` is not stored in this table. It belongs to the client authorization transaction and is
returned unchanged by the authorization endpoint. OAuth scopes are also not stored because the
current server rejects every non-empty scope request. A future scope implementation must persist
the authorized scope set with the code so the token endpoint can issue only the permissions
approved during authorization.

## Refresh sessions

Every successful login creates a separate refresh-session row.

A user may have multiple active sessions.

Important fields include:

* `id`: stable login-session identifier;
* `user_id`: session owner;
* `token_hash`: current refresh-token hash;
* `previous_token_hash`: immediately previous token hash;
* `expires_at`: sliding inactivity expiration;
* `absolute_expires_at`: fixed session expiration;
* `last_used_at`: latest successful use;
* `rotated_at`: latest rotation time;
* `revoked_at`: optional revocation time.

Plaintext refresh tokens are never stored.

A session is active when:

```text
revoked_at is null
and expires_at is in the future
and absolute_expires_at is in the future
```

Refresh rows are locked with `SELECT ... FOR UPDATE` during rotation.

A successful rotation:

1. moves the current hash to `previous_token_hash`;
2. stores the new refresh-token hash;
3. updates expiration and usage timestamps;
4. commits the transaction.

The sliding expiration never exceeds the absolute expiration.

`user_id` is not unique because multiple sessions per user are supported.

Revocation prevents future refreshes. Access-token requests do not query this table.

## API keys

The `api_keys` table stores:

* owner;
* label;
* SHA-256 key hash;
* active state;
* timestamps.

The plaintext key is returned only when the key is created.

## Todos

The `todos` table stores:

* owner;
* title and optional description;
* status and priority;
* optional due and completion timestamps;
* archive state;
* creation and update timestamps.

Every Todo belongs to one user through `user_id`.

Todo queries include both the Todo ID and owner ID so users cannot read, update, or delete
another user's records.

The service manages state-dependent values such as the completion timestamp.

## Transactions

Write services commit successful changes.

The database-session dependency rolls back the active transaction when an exception
propagates during request processing.

## Cleanup

Expired authorization codes and old revoked refresh sessions may be deleted periodically.

Expired authorization codes are also pruned opportunistically when a new code is issued.

Cleanup is not required for authentication correctness because expiration and revocation are
checked when a refresh token is used.
