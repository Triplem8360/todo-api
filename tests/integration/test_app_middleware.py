from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient

from todo_api.observability.request_context import (
    PROCESS_TIME_HEADER,
    REQUEST_ID_HEADER,
)


def test_application_adds_observability_headers(client: TestClient) -> None:
    print(client.get("/docs"))
    response = client.get("/api/v1/health")

    assert response.status_code == 200

    process_time = float(response.headers[PROCESS_TIME_HEADER])
    request_id = response.headers[REQUEST_ID_HEADER]

    assert process_time >= 0
    assert str(UUID(request_id)) == request_id
