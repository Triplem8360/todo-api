from __future__ import annotations

from fastapi import status
from fastapi.testclient import TestClient


def test_allows_configured_host(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health",
        headers={"Host": "testserver"},
    )

    assert response.status_code == status.HTTP_200_OK


def test_rejects_untrusted_host(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health",
        headers={"Host": "attacker.example"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.text == "Invalid host header"
