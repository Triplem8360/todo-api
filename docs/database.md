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
* `api_keys`.

## Users

The `users` table stores:

* normalized email;
* Argon2 password hash;
* profile fields;
* active and superuser flags;
* timestamps.

The email unique constraint provides both uniqueness and an indexed lookup.

Deleting a user cascades to their refresh sessions and API keys.

## Refresh sessions

Every successful login creates a separate refresh-session row.

A user may have multiple active sessions at the same time.

Important fields include:

* `id`: stable login-session identifier;
* `user_id`: session owner;
* `token_hash`: current refresh-token hash;
* `previous_token_hash`: immediately previous token hash;
* `expires_at`: sliding inactivity expiration;
* `absolute_expires_at`: fixed maximum session expiration;
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
3. updates the sliding expiration;
4. updates usage and rotation timestamps;
5. commits the transaction.

The sliding expiration must never exceed the absolute expiration.

Indexes support:

* lookup by session ID;
* lookup by user and revocation state;
* expired-session cleanup.

`user_id` is not unique because multiple sessions per user are supported.

Revoking a refresh session prevents future refreshes. Access-token requests do not query
this table.

## API keys

The `api_keys` table stores:

* owner;
* label;
* SHA-256 key hash;
* active state;
* timestamps.

The plaintext key is returned only when the key is created.

## Cleanup

Expired and old revoked refresh sessions may be deleted periodically.

Cleanup is not required for authentication correctness because expiration and revocation are
checked when a refresh token is used.
