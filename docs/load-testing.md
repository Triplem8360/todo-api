# Load testing with Locust

Locust is a Python-based load generator. Each `HttpUser` represents one concurrent client running
inside a lightweight greenlet. A user repeatedly selects a weighted task, sends HTTP requests,
and waits for the configured think time before selecting another task. Locust reports throughput,
response-time percentiles, and failures through a web UI or headless output.

Run these tests only against systems you own or are explicitly authorized to test. The supplied
profile creates and deletes test data and is intended for an isolated local or staging database,
never a production database.

## Test architecture

The optional `loadtest` Compose profile adds two services to the development stack:

| Service | Purpose |
| --- | --- |
| `loadtest-seed` | Recreates deterministic, verified, active users and their initial Todos. |
| `locust` | Runs `loadtests/locustfile.py` from the pinned `locustio/locust:2.46.2` image. |

The Locust container sends requests to `http://api:8000`. It waits until the API health check
passes and the seed job exits successfully. The seed job deletes the previous users matching the
selected seed (`seed-<seed>-...@example.com`) before recreating them, so each run starts from a
known state.

The normal development stack is unchanged unless the `loadtest` profile is enabled.

## Interactive web UI

Create a local load-test configuration and start the profile:

```bash
cp loadtests/.env.example loadtests/.env
docker compose \
  --env-file loadtests/.env \
  -f compose.dev.yaml \
  --profile loadtest \
  up --build
```

Open `http://localhost:8089`. The host is preconfigured as `http://api:8000`. Start with a small
smoke load, such as 5 users at 1 user per second, before increasing concurrency. Keep the requested
user count at or below `LOCUST_TEST_USER_COUNT` to give each simulated user separate credentials.
Larger values intentionally cycle through the credential pool and can introduce same-account
races.

Stop the entire stack while preserving its named volumes with:

```bash
docker compose \
  --env-file loadtests/.env \
  -f compose.dev.yaml \
  --profile loadtest \
  down
```

## Headless and repeatable runs

Headless mode is appropriate for repeatable local comparisons and CI jobs:

```bash
docker compose \
  --env-file loadtests/.env \
  -f compose.dev.yaml \
  --profile loadtest \
  run --rm locust \
  --headless \
  --users 25 \
  --spawn-rate 5 \
  --run-time 5m \
  --csv /mnt/locust/results/todo-api \
  --csv-full-history \
  --html /mnt/locust/results/todo-api.html
```

Compose starts the required services and seed job before Locust. Generated CSV and HTML reports
are written to the ignored `loadtests/results/` directory. Shut down the remaining dependencies
with the `down` command after the run.

The process exits unsuccessfully when no requests are recorded, when the aggregate failure ratio
exceeds `LOCUST_FAILURE_RATIO_LIMIT`, or when aggregate p95 latency exceeds
`LOCUST_P95_MS_LIMIT`. Individual failed requests are included in the ratio. Do not loosen
thresholds merely to make a build pass; set targets from an explicit service-level objective and
compare runs made under equivalent conditions.

Use tags to isolate workload categories:

```bash
# Read-heavy run
docker compose --env-file loadtests/.env -f compose.dev.yaml --profile loadtest \
  run --rm locust --headless -u 25 -r 5 -t 5m --tags read

# Todo writes only
docker compose --env-file loadtests/.env -f compose.dev.yaml --profile loadtest \
  run --rm locust --headless -u 10 -r 2 -t 2m --tags write
```

Lifecycle requests in `on_start` and `on_stop`—login, initial Todo lookup, token refresh, and
logout—still run when task tags are selected.

## Scenario behavior

Every simulated user:

1. selects one deterministic seeded account;
2. logs in through the real password endpoint;
3. loads initial Todo IDs;
4. repeatedly executes tasks using its bearer token;
5. rotates its refresh token shortly before access-token expiration; and
6. revokes the refresh session when the user stops.

The default task distribution is:

| Task | Weight | Approximate selection share | Tags |
| --- | ---: | ---: | --- |
| List Todos with several stable filter combinations | 8 | 32% | `todo`, `read` |
| Get one owned Todo | 5 | 20% | `todo`, `read` |
| Get the current profile | 3 | 12% | `profile`, `read` |
| Create a Todo | 3 | 12% | `todo`, `write` |
| Update a Todo priority | 2 | 8% | `todo`, `write` |
| Delete an owned Todo | 2 | 8% | `todo`, `write` |
| List API keys | 1 | 4% | `api-key`, `read` |
| Check API health | 1 | 4% | `public`, `read` |

Task weights are relative probabilities, not requests per second. Actual throughput depends on
response time, think time, active user count, and occasional setup or refresh requests. Dynamic
Todo IDs are grouped under stable Locust statistic names, preventing every ID from appearing as a
separate row.

The repeated list query variants intentionally exercise Redis cache hits. Todo writes invalidate
that user's cached reads, so this mixed workload also measures invalidation and database fallback.

The default scenario excludes registration and email verification because they create accounts,
send messages, and measure SMTP behavior rather than steady API traffic. It also excludes account
deactivation, API-key creation/revocation, browser-cookie CSRF flows, and the interactive OAuth
authorization flow. Those destructive or protocol-specific behaviors should have separate,
purpose-built scenarios and isolated data.

## Configuration

Copy `loadtests/.env.example` to the ignored `loadtests/.env` and adjust. Compose provides smaller
fallbacks when this file is omitted; the values below are the supplied example values:

| Variable | Example | Meaning |
| --- | ---: | --- |
| `LOCUST_WEB_PORT` | `8089` | Loopback port exposing the Locust UI. |
| `LOCUST_USERS` | `5` | Peak users for an autostart run; the web UI can override it. |
| `LOCUST_SPAWN_RATE` | `1` | Users started per second during an autostart ramp. |
| `LOCUST_RUN_TIME` | `25s` | Duration of an autostart run. |
| `LOCUST_AUTOSTART` | `false` | Start automatically while retaining the web UI. |
| `LOCUST_TEST_SEED` | `9001` | Deterministic seed used in account email addresses and fake data. |
| `LOCUST_TEST_USER_COUNT` | `1000` | Verified active accounts created for the credential pool. |
| `LOCUST_TEST_PASSWORD` | `LocustPass123!` | Password assigned to every load-test account. Do not reuse a real password. |
| `LOCUST_SEED_TODOS_PER_USER` | `40` | Initial Todos created per account. |
| `LOCUST_MIN_WAIT_SECONDS` | `0.5` | Minimum think time after a task. |
| `LOCUST_MAX_WAIT_SECONDS` | `2.0` | Maximum think time after a task. |
| `LOCUST_MAX_TRACKED_TODOS` | `50` | Maximum Todo IDs retained in each simulated user's local list. |
| `LOCUST_FAILURE_RATIO_LIMIT` | `0.01` | Aggregate failure-ratio threshold; `0.01` means 1%. |
| `LOCUST_P95_MS_LIMIT` | `750` | Aggregate 95th-percentile latency threshold in milliseconds. |

Locust's standard command-line flags override its runtime behavior. The important ones are:

| Flag | Meaning |
| --- | --- |
| `-u`, `--users` | Peak number of concurrently active simulated users. |
| `-r`, `--spawn-rate` | Number of new users started per second during ramp-up. |
| `-t`, `--run-time` | Duration of a headless run, such as `30s`, `5m`, or `1h`. |
| `--tags` / `--exclude-tags` | Include or exclude tagged tasks. |
| `--csv` | Write statistics, history, failures, and exceptions as CSV files. |
| `--html` | Write a standalone HTML report. |

## Reading the results

- **Requests per second (RPS)** is an observed result, not the configured user count. More users do
  not guarantee proportionally higher throughput once a bottleneck is saturated.
- **Median/p50** describes a typical request. **p95** and **p99** expose slow-tail behavior hidden
  by averages. For example, p95 of 400 ms means 95% of requests completed in 400 ms or less.
- **Failure ratio** includes unexpected HTTP statuses, invalid response shapes explicitly marked by
  the scenario, connection failures, and timeouts.
- **Current users** shows concurrency after ramp-up. **Spawn rate** controls how quickly that level
  is reached; it is not request throughput.
- A user whose `on_start` login fails stops before running tasks. Confirm the achieved user count
  in `_stats_history.csv`; the requested peak alone does not prove steady-state concurrency.

Correlate Locust results with the API's `http://localhost:8000/metrics`, application logs,
PostgreSQL activity, Redis metrics, host CPU, memory, and network utilization. If the Locust
container reaches a CPU limit before the API does, the load generator—not the API—is the
bottleneck; use distributed Locust workers or a larger external generator for higher loads.

Use a progression instead of jumping directly to a large test:

1. **Smoke:** 1–5 users for about 30 seconds to validate the scenario.
2. **Baseline:** expected normal concurrency at a slow ramp rate.
3. **Load:** expected peak traffic for a steady measurement window.
4. **Stress:** increase users gradually until latency or failures cross the objective.
5. **Soak:** hold expected load for a long period to find leaks and resource exhaustion.

Local results are development signals, not production capacity claims. Verify the effective API
worker count, database pools, resource limits, network latency, TLS, proxies, and observability
settings before comparing local results with production.

For Locust's underlying behavior and additional options, see the official documentation for
[writing a locustfile](https://docs.locust.io/en/stable/writing-a-locustfile.html),
[configuration](https://docs.locust.io/en/stable/configuration.html), and
[Docker execution](https://docs.locust.io/en/stable/running-in-docker.html).
