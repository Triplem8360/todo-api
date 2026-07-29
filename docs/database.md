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
* `api_keys`;
* `todos`.

## Users

The `users` table stores:

* normalized email;
* Argon2 password hash;
* profile fields;
* active and superuser flags;
* timestamps.

The email unique constraint provides uniqueness and an indexed lookup.

Deleting a user cascades to their refresh sessions, API keys, and Todos.

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

Expired and old revoked refresh sessions may be deleted periodically.

Cleanup is not required for authentication correctness because expiration and revocation are
checked when a refresh token is used.
