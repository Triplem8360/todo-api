# Celery background tasks

Celery moves SMTP and database maintenance work out of the FastAPI processes. The API publishes
request-driven email tasks, Celery Beat publishes periodic maintenance tasks, dedicated workers
consume each queue, and Celery keeps final states and results in Redis for a limited time.

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

Celery Beat (one process per deployment)
  -> publish due maintenance task to the maintenance queue in Redis DB 2
  -> dedicated maintenance worker runs one idempotent database transaction
  -> store the affected-row count in Redis DB 3
```

The task names are stable and may be used by monitoring tools:

* `todo_api.email.send_registration_verification_email`
* `todo_api.email.send_registration_welcome_email`
* `todo_api.maintenance.clear_expired_email_verification_tokens`
* `todo_api.maintenance.auto_archive_completed_todos`

Task definitions live in `todo_api.background.tasks.email` and
`todo_api.background.tasks.maintenance`. `background.dispatch` is the producer-side adapter used
by the API: it runs Celery's synchronous `apply_async` call in a thread pool, disables slow publish
retries during a request, redacts every argument from Celery event representations, logs the task
ID, and converts broker publication failures into the boolean queue status returned by the
registration flow. Keeping this separate prevents worker implementation details and blocking
broker calls from spreading through async route handlers.

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

## Periodic maintenance

Celery Beat uses UTC and publishes these entries from the application configuration:

| Job | Schedule | Purpose |
| --- | --- | --- |
| Clear email-verification tokens | Every 30 seconds | Remove expired token hashes and let pending users request a fresh link. |
| Auto-archive completed Todos | Daily at 02:30 | Archive completed, unarchived Todos older than the retention setting. |

Both tasks are set-based, transactional, and idempotent. Database failures retry up to three
times with exponential backoff and jitter. Every Beat message has an expiry shorter than its next
useful run, which prevents stale maintenance jobs from piling up during a prolonged outage. Each
result includes an `operation` name and `affected` row count.

The maintenance queue has a dedicated worker with a default concurrency of one. Its child process
creates one long-lived `asyncio.Runner` after Celery forks, lazily creates one SQLAlchemy async
engine on the same event loop, and reuses both for subsequent maintenance tasks. Graceful worker
shutdown disposes the engine on its owning loop before closing the loop. This avoids per-task pool
and connection setup without sharing async connections across processes or with the API.

Auto-archiving only changes `is_archived`; it does not delete a Todo, and a client can unarchive it
through the normal update endpoint. The query uses a composite status/archive/completion index.
Set `COMPLETED_TODO_AUTO_ARCHIVE_DAYS=0` to leave completed Todos unchanged while retaining the
security cleanup jobs.

OAuth authorization-code and refresh-session pruning remain owned by the API's Redis-backed
APScheduler, at five-minute and ten-second intervals respectively. They are intentionally not
registered as Celery tasks or Beat entries, preventing duplicate pruning. APScheduler stores its
jobs and run-time index in Redis logical DB 1 under the configured `APSCHEDULER_*_KEY` values.

## Configuration

```env
APSCHEDULER_REDIS_DB=1
APSCHEDULER_JOBS_KEY=todo-api:apscheduler:jobs
APSCHEDULER_RUN_TIMES_KEY=todo-api:apscheduler:run-times
CELERY_BROKER_URL=redis://localhost:6379/2
CELERY_RESULT_BACKEND=redis://localhost:6379/3
CELERY_RESULT_EXPIRES_SECONDS=3600
CELERY_TASK_ALWAYS_EAGER=false
CELERY_WORKER_CONCURRENCY=2
CELERY_MAINTENANCE_WORKER_CONCURRENCY=1
COMPLETED_TODO_AUTO_ARCHIVE_DAYS=30
```

`CELERY_RESULT_BACKEND` is Celery's established configuration name, parallel to
`CELERY_BROKER_URL`. The value is already a URL; renaming it to
`CELERY_RESULT_BACKEND_URL` would create a project-specific alias without improving clarity.

The Compose files replace `localhost` with the `redis` service hostname. Logical DB 0 remains the
Todo cache, DB 1 stores APScheduler state, DB 2 is the Celery broker, and DB 3 is the result
backend. Logical databases separate keys but do not provide resource or security isolation;
production deployments with substantial traffic should use a dedicated Redis service for Celery.

Every current task has an explicit route. The general worker consumes `default` and `emails`, while
the maintenance worker consumes only `maintenance`. The `default` queue remains a fallback for a
future registered task that has not received a dedicated route yet.

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
docker compose -f compose.dev.yaml logs -f \
  api celery-worker celery-maintenance-worker celery-beat
```

Run exactly one `celery-beat` replica. Multiple Beat replicas publish the same schedule more than
once; the maintenance operations remain safe but create unnecessary database and broker load.

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

The same inspection commands can target `celery-maintenance-worker` when diagnosing maintenance
jobs.

Inspect the Redis queue and result keys without changing them:

```bash
docker compose -f compose.dev.yaml exec redis redis-cli -n 2 LLEN emails
docker compose -f compose.dev.yaml exec redis redis-cli -n 2 LLEN default
docker compose -f compose.dev.yaml exec redis redis-cli -n 2 LLEN maintenance
docker compose -f compose.dev.yaml exec redis \
  redis-cli -n 3 --scan --pattern 'celery-task-meta-*'
```

Scale workers when the email backlog grows:

```bash
docker compose -f compose.dev.yaml up -d --scale celery-worker=3
```

`celery-worker` consumes `default` and `emails`; `celery-maintenance-worker` consumes only
`maintenance`. Scale general workers as needed, but keep maintenance concurrency at one unless the
database capacity and operations have been reviewed for safe parallel execution.

Run a task manually from the host for SMTP testing. The command prints a task ID:

```bash
uv run celery -A todo_api.background.celery_app:celery_app call \
  todo_api.email.send_registration_welcome_email \
  --kwargs='{"recipient":"user@example.com","full_name":"Test User"}'
```

Use that ID to inspect the short-lived result:

```bash
uv run celery -A todo_api.background.celery_app:celery_app result <task-id>
```

Run a Beat-owned maintenance task immediately and inspect its affected-row count:

```bash
uv run celery -A todo_api.background.celery_app:celery_app call \
  todo_api.maintenance.clear_expired_email_verification_tokens \
  --queue maintenance
```

For deterministic tests, `CELERY_TASK_ALWAYS_EAGER=true` executes tasks in the publisher instead of
using Redis. Do not enable eager mode in a deployed API because email delivery would once again
block request processing. The unit suite mocks publishing and SMTP delivery and can be run with:

```bash
uv run pytest tests/unit/test_celery_tasks.py tests/unit/test_maintenance_repositories.py \
  tests/api/test_registration_email_verification.py
```

## Redis durability

The bundled Redis uses append-only persistence with an `everysec` fsync policy and a named volume.
It also uses `noeviction`: silently evicting a broker message would lose work. When the configured
memory limit is reached, Redis rejects new writes instead, allowing the API to report
`verification_email_queued: false` and operators to address capacity. Task results expire after
`CELERY_RESULT_EXPIRES_SECONDS`, limiting DB 3 growth.
