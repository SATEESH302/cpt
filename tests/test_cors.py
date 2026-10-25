import pytest
from fastapi.testclient import TestClient


def test_allowed_origin(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={
        "Origin": "http://localhost:5173"
    })
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "X-Request-ID" in response.headers["access-control-expose-headers"]


def test_disallowed_origin(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "https://evil.test"})
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_preflight(client: TestClient, method: str) -> None:
    response = client.options("/api/v1/health", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert method in response.headers["access-control-allow-methods"]
    assert response.headers["x-request-id"]


def test_disallowed_preflight(client: TestClient) -> None:
    response = client.options("/api/v1/health", headers={
        "Origin": "https://evil.test", "Access-Control-Request-Method": "GET"
    })
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
    assert response.json()["error"]["code"] == "CORS_REQUEST_DENIED"
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_cors_on_unexpected_error(client: TestClient) -> None:
    response = client.get("/_test/unexpected", headers={
        "Origin": "http://localhost:5173"
    })
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
