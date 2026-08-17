from __future__ import annotations

import itertools
import os
import random
from collections.abc import Callable
from time import monotonic
from uuid import uuid4

from locust import HttpUser, between, events, tag, task
from locust.exception import StopUser

JsonConsumer = Callable[[object], bool]

PRIORITIES = ("low", "medium", "high")
TODO_LIST_QUERIES = (
    {"limit": 20, "offset": 0},
    {"limit": 20, "offset": 0, "priority": "high"},
    {"limit": 20, "offset": 0, "status": "todo"},
    {"limit": 20, "offset": 0, "sort_by": "title", "sort_direction": "asc"},
)
TOKEN_REFRESH_MARGIN_SECONDS = 30


def _integer_setting(name: str, default: int, *, minimum: int = 1) -> int:
    value = int(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _float_setting(name: str, default: float, *, minimum: float = 0) -> float:
    value = float(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


TEST_SEED = _integer_setting("LOCUST_TEST_SEED", 9001, minimum=0)
TEST_USER_COUNT = _integer_setting("LOCUST_TEST_USER_COUNT", 50)
TEST_PASSWORD = os.getenv("LOCUST_TEST_PASSWORD", "LocustPass123!")
MIN_WAIT_SECONDS = _float_setting("LOCUST_MIN_WAIT_SECONDS", 0.5)
MAX_WAIT_SECONDS = _float_setting("LOCUST_MAX_WAIT_SECONDS", 2.0)
MAX_TRACKED_TODOS = _integer_setting("LOCUST_MAX_TRACKED_TODOS", 50)
FAILURE_RATIO_LIMIT = _float_setting("LOCUST_FAILURE_RATIO_LIMIT", 0.01)
P95_MS_LIMIT = _float_setting("LOCUST_P95_MS_LIMIT", 750)

if not TEST_PASSWORD:
    raise ValueError("LOCUST_TEST_PASSWORD must not be empty")
if MAX_WAIT_SECONDS < MIN_WAIT_SECONDS:
    raise ValueError("LOCUST_MAX_WAIT_SECONDS must be greater than or equal to the minimum")
if FAILURE_RATIO_LIMIT > 1:
    raise ValueError("LOCUST_FAILURE_RATIO_LIMIT must be between zero and one")


_user_sequence = itertools.count()


class TodoApiUser(HttpUser):
    """Exercise a representative authenticated Todo API workload."""

    wait_time = between(MIN_WAIT_SECONDS, MAX_WAIT_SECONDS)

    access_token: str
    refresh_token: str
    refresh_at: float
    todo_ids: list[int]

    def on_start(self) -> None:
        credential_index = next(_user_sequence) % TEST_USER_COUNT + 1
        self.email = f"seed-{TEST_SEED}-{credential_index:04d}@example.com"
        self.todo_ids = []

        if not self._login():
            raise StopUser()
        self._load_todo_ids()

    def on_stop(self) -> None:
        if refresh_token := getattr(self, "refresh_token", None):
            self._request(
                "POST",
                "/api/v1/auth/logout",
                204,
                authenticated=False,
                json={"refresh_token": refresh_token},
            )

    def _request(
        self,
        method: str,
        path: str,
        expected_status: int,
        *,
        authenticated: bool = True,
        consume_json: JsonConsumer | None = None,
        name: str | None = None,
        **kwargs: object,
    ) -> bool:
        if authenticated:
            kwargs["headers"] = self._headers()

        with self.client.request(
            method,
            path,
            name=name or path,
            catch_response=True,
            **kwargs,
        ) as response:
            if response.status_code != expected_status:
                response.failure(f"expected {expected_status}, received {response.status_code}")
                return False

            if consume_json is None:
                return True

            try:
                payload = response.json()
            except ValueError:
                response.failure("response is not valid JSON")
                return False

            if not consume_json(payload):
                response.failure("response payload is invalid")
                return False

        return True

    def _login(self) -> bool:
        return self._request(
            "POST",
            "/api/v1/auth/login",
            200,
            authenticated=False,
            consume_json=self._store_tokens,
            data={"username": self.email, "password": TEST_PASSWORD},
        )

    def _store_tokens(self, payload: object) -> bool:
        if not isinstance(payload, dict):
            return False

        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        expires_in = payload.get("expires_in")
        if not (
            isinstance(access_token, str)
            and access_token
            and isinstance(refresh_token, str)
            and refresh_token
            and isinstance(expires_in, int)
            and not isinstance(expires_in, bool)
            and expires_in > 0
        ):
            return False

        self.access_token = access_token
        self.refresh_token = refresh_token
        self.refresh_at = monotonic() + max(1, expires_in - TOKEN_REFRESH_MARGIN_SECONDS)
        return True

    def _ensure_access_token(self) -> None:
        if monotonic() < self.refresh_at:
            return

        if not self._request(
            "POST",
            "/api/v1/auth/refresh",
            200,
            authenticated=False,
            consume_json=self._store_tokens,
            json={"refresh_token": self.refresh_token},
        ):
            raise StopUser()

    def _headers(self) -> dict[str, str]:
        self._ensure_access_token()
        return {"Authorization": f"Bearer {self.access_token}"}

    def _remember_todo_id(self, todo_id: int) -> None:
        if todo_id not in self.todo_ids:
            self.todo_ids.append(todo_id)
        del self.todo_ids[:-MAX_TRACKED_TODOS]

    def _remember_todos(self, payload: object) -> bool:
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            return False

        for item in payload["items"]:
            todo_id = item.get("id") if isinstance(item, dict) else None
            if isinstance(todo_id, int) and not isinstance(todo_id, bool):
                self._remember_todo_id(todo_id)
        return True

    def _remember_created_todo(self, payload: object) -> bool:
        todo_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(todo_id, int) or isinstance(todo_id, bool):
            return False
        self._remember_todo_id(todo_id)
        return True

    def _load_todo_ids(self) -> None:
        self._request(
            "GET",
            "/api/v1/todos",
            200,
            consume_json=self._remember_todos,
            name="/api/v1/todos [list]",
            params={"limit": min(MAX_TRACKED_TODOS, 100), "offset": 0},
        )

    def _random_todo_id(self) -> int | None:
        if not self.todo_ids:
            self._load_todo_ids()
        return random.choice(self.todo_ids) if self.todo_ids else None

    @tag("public", "read")
    @task(1)
    def health(self) -> None:
        self._request("GET", "/api/v1/health", 200, authenticated=False)

    @tag("profile", "read")
    @task(3)
    def profile(self) -> None:
        self._request("GET", "/api/v1/users/me", 200)

    @tag("api-key", "read")
    @task(1)
    def list_api_keys(self) -> None:
        self._request(
            "GET",
            "/api/v1/api-keys",
            200,
            name="/api/v1/api-keys [list]",
        )

    @tag("todo", "read")
    @task(8)
    def list_todos(self) -> None:
        self._request(
            "GET",
            "/api/v1/todos",
            200,
            consume_json=self._remember_todos,
            name="/api/v1/todos [list]",
            params=random.choice(TODO_LIST_QUERIES),
        )

    @tag("todo", "read")
    @task(5)
    def get_todo(self) -> None:
        if todo_id := self._random_todo_id():
            self._request(
                "GET",
                f"/api/v1/todos/{todo_id}",
                200,
                name="/api/v1/todos/{todo_id} [get]",
            )

    @tag("todo", "write")
    @task(3)
    def create_todo(self) -> None:
        self._request(
            "POST",
            "/api/v1/todos",
            201,
            consume_json=self._remember_created_todo,
            name="/api/v1/todos [create]",
            json={
                "title": f"Locust todo {uuid4().hex[:12]}",
                "description": "Created by the controlled Locust load test.",
                "priority": random.choice(PRIORITIES),
            },
        )

    @tag("todo", "write")
    @task(2)
    def update_todo(self) -> None:
        if todo_id := self._random_todo_id():
            self._request(
                "PATCH",
                f"/api/v1/todos/{todo_id}",
                200,
                name="/api/v1/todos/{todo_id} [update]",
                json={"priority": random.choice(PRIORITIES)},
            )

    @tag("todo", "write")
    @task(2)
    def delete_todo(self) -> None:
        if (todo_id := self._random_todo_id()) and self._request(
            "DELETE",
            f"/api/v1/todos/{todo_id}",
            204,
            name="/api/v1/todos/{todo_id} [delete]",
        ):
            self.todo_ids.remove(todo_id)


@events.test_start.add_listener
def reset_user_sequence(**_: object) -> None:
    global _user_sequence
    _user_sequence = itertools.count()


@events.quitting.add_listener
def enforce_service_level_thresholds(environment, **_: object) -> None:
    stats = environment.stats.total
    breaches: list[str] = []

    if stats.num_requests == 0:
        breaches.append("no requests were recorded")
    else:
        if stats.fail_ratio > FAILURE_RATIO_LIMIT:
            breaches.append(
                f"failure ratio {stats.fail_ratio:.2%} exceeded {FAILURE_RATIO_LIMIT:.2%}"
            )

        p95_ms = stats.get_response_time_percentile(0.95)
        if p95_ms > P95_MS_LIMIT:
            breaches.append(f"p95 response time {p95_ms} ms exceeded {P95_MS_LIMIT:g} ms")

    if breaches:
        environment.process_exit_code = 1
        print("Load-test thresholds failed: " + "; ".join(breaches))
