from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import FastAPI, Request, status
from fastapi.testclient import TestClient

from todo_api.observability.request_context import (
    PROCESS_TIME_HEADER,
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
)


def create_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/probe")
    async def probe(request: Request) -> dict[str, str]:
        return {"request_id": request.state.request_id}

    return app


def test_adds_observability_headers() -> None:
    with TestClient(create_test_app()) as client:
        response = client.get("/probe")

    assert response.status_code == status.HTTP_200_OK
    assert float(response.headers[PROCESS_TIME_HEADER]) >= 0

    request_id = response.headers[REQUEST_ID_HEADER]
    assert str(UUID(request_id)) == request_id
    assert response.json()["request_id"] == request_id


def test_preserves_valid_request_id() -> None:
    request_id = str(uuid4())

    with TestClient(create_test_app()) as client:
        response = client.get(
            "/probe",
            headers={REQUEST_ID_HEADER: request_id},
        )

    assert response.headers[REQUEST_ID_HEADER] == request_id
    assert response.json()["request_id"] == request_id


def test_replaces_invalid_request_id() -> None:
    with TestClient(create_test_app()) as client:
        response = client.get(
            "/probe",
            headers={REQUEST_ID_HEADER: "not-a-valid-uuid"},
        )

    returned_request_id = response.headers[REQUEST_ID_HEADER]

    assert returned_request_id != "not-a-valid-uuid"
    assert str(UUID(returned_request_id)) == returned_request_id
