# Celery background tasks

Celery moves SMTP work out of the FastAPI processes. The API publishes a small JSON task to
Redis, a dedicated worker performs the SMTP exchange, and Celery writes the final state and result
back to Redis for a limited time.

## Runtime flow

```text
registration request
  -> commit the unverified user and hashed verification token
  -> publish send_registration_verification_email to Redis DB 2
  -> return the API response
  -> Celery worker sends the multipart email through SMTP
  -> store SUCCESS, RETRY, or FAILURE and the task result in Redis DB 3

verification link
  -> atomically mark the email address verified
  -> publish send_registration_welcome_email to Redis DB 2
  -> Celery worker sends the welcome message
```

The task names are stable and may be used by monitoring tools:

* `todo_api.send_registration_verification_email`
* `todo_api.send_registration_welcome_email`

Task definitions live in `todo_api.background.tasks.email`. `background.dispatch` is the
producer-side adapter used by the API: it runs Celery's synchronous `apply_async` call in a thread
pool, disables slow publish retries during a request, redacts every argument from Celery event
representations, logs the task ID, and converts broker publication failures into the boolean queue
status returned by the registration flow. Keeping this separate prevents worker implementation
details and blocking broker calls from spreading through async route handlers.

Every published email task carries the API request ID in its message headers. Verification-email
tasks also expire when their verification token expires, preventing a delayed worker from sending
an already-useless link after a long queue backlog.

Both tasks accept JSON-compatible primitives, build HTML and plain-text message bodies inside the
worker, and return a small result such as
`{"delivered": true, "email_type": "registration_welcome"}`. SMTP service errors retry up to five
times with exponential backoff and jitter. Workers acknowledge tasks after execution and use a
prefetch multiplier of one, which improves recovery and avoids one worker reserving many SMTP jobs.

Celery provides at-least-once execution, not exactly-once delivery. A worker loss after the SMTP
server accepts a message but before the Redis acknowledgement can produce a duplicate email. The
verification token itself remains single-use, so a duplicate verification message does not create
another account or make the token reusable.

## Configuration

```env
CELERY_BROKER_URL=redis://localhost:6379/2
CELERY_RESULT_BACKEND=redis://localhost:6379/3
CELERY_RESULT_EXPIRES_SECONDS=3600
CELERY_TASK_ALWAYS_EAGER=false
```

`CELERY_RESULT_BACKEND` is Celery's established configuration name, parallel to
`CELERY_BROKER_URL`. The value is already a URL; renaming it to
`CELERY_RESULT_BACKEND_URL` would create a project-specific alias without improving clarity.

The Compose files replace `localhost` with the `redis` service hostname. Logical DB 0 remains the
Todo cache, DB 1 stores APScheduler state, DB 2 is the Celery broker, and DB 3 is the result backend.
Logical databases separate keys but do not provide resource or security isolation; production
deployments with substantial traffic should use a dedicated Redis service for Celery.

The registration response exposes `verification_email_queued`. It is `true` only when Redis accepts
the publish. The older `verification_email_sent` field remains as a deprecated alias for client
compatibility; it no longer proves that SMTP delivery completed. Resend always returns the same
`202` body to avoid account enumeration, even if the task cannot be published.

Task arguments include the email recipient and, for verification mail, the raw single-use token.
Celery event representations redact those arguments, but Redis must still be treated as sensitive
infrastructure. Restrict network access and use authenticated
`rediss://...?...ssl_cert_reqs=required` endpoints in production.

## Run and inspect

Start the complete development stack:

```bash
docker compose -f compose.dev.yaml up --build -d
docker compose -f compose.dev.yaml logs -f api celery-worker
```

Inspect worker availability and queues:

```bash
docker compose -f compose.dev.yaml exec celery-worker \
  celery -A todo_api.background.celery_app:celery_app inspect ping
docker compose -f compose.dev.yaml exec celery-worker \
  celery -A todo_api.background.celery_app:celery_app inspect registered
docker compose -f compose.dev.yaml exec celery-worker \
  celery -A todo_api.background.celery_app:celery_app inspect active
docker compose -f compose.dev.yaml exec celery-worker \
  celery -A todo_api.background.celery_app:celery_app inspect reserved
```

Inspect the Redis queue and result keys without changing them:

```bash
docker compose -f compose.dev.yaml exec redis redis-cli -n 2 LLEN emails
docker compose -f compose.dev.yaml exec redis \
  redis-cli -n 3 --scan --pattern 'celery-task-meta-*'
```

Scale workers when the email backlog grows:

```bash
docker compose -f compose.dev.yaml up -d --scale celery-worker=3
```

Run a task manually from the host for SMTP testing. The command prints a task ID:

```bash
uv run celery -A todo_api.background.celery_app:celery_app call \
  todo_api.send_registration_welcome_email \
  --kwargs='{"recipient":"user@example.com","full_name":"Test User"}'
```

Use that ID to inspect the short-lived result:

```bash
uv run celery -A todo_api.background.celery_app:celery_app result <task-id>
```

For deterministic tests, `CELERY_TASK_ALWAYS_EAGER=true` executes tasks in the publisher instead of
using Redis. Do not enable eager mode in a deployed API because email delivery would once again
block request processing. The unit suite mocks publishing and SMTP delivery and can be run with:

```bash
uv run pytest tests/unit/test_celery_tasks.py tests/api/test_registration_email_verification.py
```

## Redis durability

The bundled Redis uses append-only persistence with an `everysec` fsync policy and a named volume.
It also uses `noeviction`: silently evicting a broker message would lose work. When the configured
memory limit is reached, Redis rejects new writes instead, allowing the API to report
`verification_email_queued: false` and operators to address capacity. Task results expire after
`CELERY_RESULT_EXPIRES_SECONDS`, limiting DB 3 growth.
