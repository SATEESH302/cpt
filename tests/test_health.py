from uuid import UUID

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.schemas.health import HealthResponse


def test_health(client: TestClient, settings: Settings) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy", "service": settings.service_name,
        "version": settings.app_version,
    }
    assert HealthResponse.model_validate(response.json()).status == "healthy"
    UUID(response.headers["x-request-id"])


def test_configured_health_and_prefix() -> None:
    from app.main import create_app

    settings = Settings(
        _env_file=None, api_v1_prefix="/custom/v1",
        app_version="2.0.0", service_name="configured-service",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/custom/v1/health")
        assert response.json()["version"] == "2.0.0"
        assert response.json()["service"] == "configured-service"
        assert client.get("/api/v1/health").status_code == 404


def test_request_ids_are_generated_per_request(client: TestClient) -> None:
    first = client.get("/api/v1/health", headers={"X-Request-ID": "untrusted"})
    second = client.get("/api/v1/health")
    assert first.headers["x-request-id"] != "untrusted"
    assert first.headers["x-request-id"] != second.headers["x-request-id"]
