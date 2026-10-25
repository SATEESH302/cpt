import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
def test_documentation(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_openapi(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "Diagnostic Platform API"
    assert schema["info"]["version"] == "1.0.0"
    endpoint = schema["paths"]["/api/v1/health"]["get"]
    assert endpoint["tags"] == ["Health"]
    assert endpoint["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HealthResponse"
    }
    assert endpoint["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }


def test_production_routes_only() -> None:
    from app.main import create_app
    from app.core.config import Settings

    application = create_app(Settings(_env_file=None, app_env="production"))
    assert set(application.openapi()["paths"]) == {
        "/api/v1/health", "/api/v1/diagnostic-tests",
        "/api/v1/diagnostic-tests/search", "/api/v1/diagnostic-tests/{test_id}",
        "/api/v1/auth/csrf", "/api/v1/auth/register", "/api/v1/auth/login",
        "/api/v1/auth/me", "/api/v1/auth/logout",
    }
    with TestClient(application) as client:
        assert client.get("/_test/unexpected").status_code == 404
