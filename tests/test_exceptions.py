from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.schemas.errors import ErrorResponse


@pytest.mark.parametrize("path,status,code,message", [
    ("/_test/http", 401, "UNAUTHORIZED", "Authentication required"),
    ("/_test/custom", 409, "RESOURCE_CONFLICT", "Resource already exists."),
    ("/missing", 404, "NOT_FOUND", "Not Found"),
    ("/_test/unexpected", 500, "INTERNAL_SERVER_ERROR",
     "An unexpected error occurred."),
])
def test_error_contract(
    client: TestClient, path: str, status: int, code: str, message: str
) -> None:
    response = client.get(path)
    assert response.status_code == status
    body = ErrorResponse.model_validate(response.json())
    assert body.success is False
    assert body.error.code == code
    assert body.error.message == message
    UUID(body.request_id)
    assert body.request_id == response.headers["x-request-id"]
    assert "secret" not in response.text
    assert "Traceback" not in response.text
    if status == 401:
        assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("payload", [{"count": "private-medical-input"}, {}])
def test_validation(client: TestClient, payload: dict) -> None:
    response = client.post("/_test/validation", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "private-medical-input" not in response.text


def test_method_not_allowed(client: TestClient) -> None:
    response = client.post("/api/v1/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert "GET" in response.headers["allow"]
