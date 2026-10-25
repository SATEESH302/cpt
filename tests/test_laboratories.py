"""Laboratory API integration tests use private SQLite tables, never MySQL."""

import io
import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    BigInteger, DefaultClause, Integer, MetaData, String, create_engine, text,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.db.session import get_db
from app.models.laboratory import Laboratory
from app.models.patient import Patient


@pytest.fixture
def laboratory_database():
    metadata = MetaData()
    for model, key in ((Laboratory, "lab_id"), (Patient, "patient_id")):
        table = model.__table__.to_metadata(metadata)
        table.c[key].type = BigInteger().with_variant(Integer, "sqlite")
        table.c.updated_at.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))
    metadata.tables["laboratories"].c.status.type = String(8)
    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    finally:
        engine.dispose()


@pytest.fixture
def lab_client(laboratory_database):
    from app.main import create_app

    application = create_app(Settings(_env_file=None, app_env="development"))

    def isolated_db():
        with laboratory_database() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise

    application.dependency_overrides[get_db] = isolated_db
    try:
        with TestClient(application) as client:
            yield client
    finally:
        application.dependency_overrides.clear()


def register(client, **changes) -> dict:
    payload = {"lab_name": "Sample Laboratory"}
    payload.update(changes)
    response = client.post("/api/v1/laboratories", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_register_defaults_and_get(lab_client) -> None:
    response = lab_client.post("/api/v1/laboratories", json={
        "lab_name": " Sample Laboratory ", "contact_person": "Test Contact",
        "phone": "+91 98765 43210", "email": "LAB@EXAMPLE.COM",
        "address": "Test address", "district": "Bengaluru", "pincode": "560001",
        "accreditation_number": "TEST-123",
    })
    assert response.status_code == 201
    laboratory = response.json()
    assert laboratory["lab_name"] == "Sample Laboratory"
    assert laboratory["status"] == "PENDING"
    assert laboratory["eligible_for_booking"] is False
    assert laboratory["email"] == "lab@example.com"
    assert laboratory["created_at"] is not None
    assert laboratory["updated_at"] is not None
    path = f"/api/v1/laboratories/{laboratory['lab_id']}"
    assert response.headers["Location"] == path
    assert response.headers["Cache-Control"] == "no-store"
    assert lab_client.get(path).json() == laboratory


def test_minimal_registration(lab_client) -> None:
    laboratory = register(lab_client)
    assert laboratory["status"] == "PENDING"
    assert laboratory["phone"] is None
    assert laboratory["email"] is None


@pytest.mark.parametrize("payload", [
    {}, {"lab_name": " "}, {"lab_name": "x" * 201},
    {"lab_name": "Lab", "email": "invalid"},
    {"lab_name": "Lab", "phone": "123"},
    {"lab_name": "Lab", "phone": "abcdefghi"},
    {"lab_name": "Lab", "pincode": "12345"},
    {"lab_name": "Lab", "pincode": "1234567"},
    {"lab_name": "Lab", "pincode": "012345"},
    {"lab_name": "Lab", "pincode": "ABCDEF"},
    {"lab_name": "Lab", "status": "ACTIVE"},
    {"lab_name": "Lab", "lab_id": 10},
    {"lab_name": "Lab", "address": "x" * 16001},
    {"lab_name": "Lab", "accreditation_number": "x" * 101},
])
def test_registration_validation(lab_client, payload) -> None:
    response = lab_client.post("/api/v1/laboratories", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["request_id"] == response.headers["x-request-id"]


@pytest.mark.parametrize("method,path,payload", [
    ("GET", "/api/v1/laboratories/999", None),
    ("PUT", "/api/v1/laboratories/999", {"lab_name": "New"}),
    ("PATCH", "/api/v1/laboratories/999/status", {"status": "ACTIVE"}),
])
def test_missing_lab(lab_client, method, path, payload) -> None:
    response = lab_client.request(method, path, json=payload)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "LABORATORY_NOT_FOUND"


@pytest.mark.parametrize("lab_id", ["0", "-1", "abc", "9223372036854775808"])
def test_invalid_ids(lab_client, lab_id) -> None:
    assert lab_client.get(f"/api/v1/laboratories/{lab_id}").status_code == 422


def test_update_partial_and_clear_optional(lab_client) -> None:
    laboratory = register(lab_client, phone="9876543210", email="lab@example.com")
    path = f"/api/v1/laboratories/{laboratory['lab_id']}"
    response = lab_client.put(path, json={
        "lab_name": "Updated Laboratory", "email": None, "pincode": "600001",
    })
    assert response.status_code == 200
    assert response.json()["lab_id"] == laboratory["lab_id"]
    assert response.json()["lab_name"] == "Updated Laboratory"
    assert response.json()["phone"] == laboratory["phone"]
    assert response.json()["email"] is None
    assert response.json()["status"] == "PENDING"
    assert lab_client.get(path).json() == response.json()


@pytest.mark.parametrize("payload", [
    {}, {"lab_name": None}, {"lab_name": " "}, {"phone": "bad"},
    {"email": "bad"}, {"pincode": "1"}, {"lab_id": 5},
    {"created_at": "2026-01-01"}, {"status": "ACTIVE"},
])
def test_invalid_updates(lab_client, payload) -> None:
    laboratory = register(lab_client)
    path = f"/api/v1/laboratories/{laboratory['lab_id']}"
    assert lab_client.put(path, json=payload).status_code == 422


def test_pagination(lab_client) -> None:
    ids = [register(lab_client, lab_name=f"Lab {i}")["lab_id"] for i in range(5)]
    first = lab_client.get("/api/v1/laboratories?page_size=2").json()
    second = lab_client.get("/api/v1/laboratories?page=2&page_size=2").json()
    assert (first["total"], first["pages"]) == (5, 3)
    assert [item["lab_id"] for item in first["items"]] == ids[:2]
    assert [item["lab_id"] for item in second["items"]] == ids[2:4]
    assert lab_client.get("/api/v1/laboratories?page=100").json()["items"] == []


def test_empty_list(lab_client) -> None:
    assert lab_client.get("/api/v1/laboratories").json() == {
        "items": [], "total": 0, "page": 1, "page_size": 20, "pages": 0,
    }


@pytest.mark.parametrize("query", ["page=0", "page_size=0", "page_size=101"])
def test_invalid_pagination(lab_client, query) -> None:
    assert lab_client.get(f"/api/v1/laboratories?{query}").status_code == 422


@pytest.mark.parametrize("term", ["Alpha", "Bengaluru", "560001"])
def test_search_name_district_pincode(lab_client, term) -> None:
    expected = register(
        lab_client, lab_name="Alpha Diagnostics", district="Bengaluru",
        pincode="560001",
    )
    register(
        lab_client, lab_name="Beta Diagnostics", district="Chennai", pincode="600001"
    )
    response = lab_client.get("/api/v1/laboratories/search", params={"q": term})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["lab_id"] == expected["lab_id"]


def test_search_pagination_and_no_results(lab_client) -> None:
    register(lab_client, lab_name="Alpha Diagnostics")
    second = register(lab_client, lab_name="Beta Diagnostics")
    response = lab_client.get("/api/v1/laboratories/search", params={
        "q": "Diagnostics", "page": 2, "page_size": 1,
    })
    assert response.json()["total"] == 2
    assert response.json()["items"][0]["lab_id"] == second["lab_id"]
    assert lab_client.get(
        "/api/v1/laboratories/search", params={"q": "unmatched"}
    ).json()["total"] == 0


@pytest.mark.parametrize("term", ["%", "_", "' OR 1=1 --"])
def test_search_literal_input(lab_client, term) -> None:
    register(lab_client)
    response = lab_client.get("/api/v1/laboratories/search", params={"q": term})
    assert response.status_code == 200
    assert response.json()["total"] == 0


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "  "}])
def test_invalid_search(lab_client, params) -> None:
    response = lab_client.get("/api/v1/laboratories/search", params=params)
    assert response.status_code == 422


def test_activate_deactivate_and_reactivate(lab_client) -> None:
    laboratory = register(lab_client)
    path = f"/api/v1/laboratories/{laboratory['lab_id']}"
    for status in ("ACTIVE", "INACTIVE", "ACTIVE", "ACTIVE"):
        response = lab_client.patch(f"{path}/status", json={"status": status})
        assert response.status_code == 200
        assert response.json()["status"] == status
        assert response.json()["eligible_for_booking"] == (status == "ACTIVE")
        assert lab_client.get(path).json()["status"] == status


def test_pending_can_be_deactivated(lab_client) -> None:
    laboratory = register(lab_client)
    response = lab_client.patch(
        f"/api/v1/laboratories/{laboratory['lab_id']}/status",
        json={"status": "INACTIVE"},
    )
    assert response.status_code == 200
    assert response.json()["eligible_for_booking"] is False


@pytest.mark.parametrize("status", ["ACTIVE", "INACTIVE"])
def test_return_to_pending_is_rejected(lab_client, status) -> None:
    laboratory = register(lab_client)
    path = f"/api/v1/laboratories/{laboratory['lab_id']}/status"
    assert lab_client.patch(path, json={"status": status}).status_code == 200
    response = lab_client.patch(path, json={"status": "PENDING"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_LABORATORY_STATUS_TRANSITION"


@pytest.mark.parametrize("payload", [
    {}, {"status": None}, {"status": "INVALID"}, {"status": "active"},
    {"status": "ACTIVE", "lab_id": 999},
])
def test_invalid_status_input(lab_client, payload) -> None:
    laboratory = register(lab_client)
    response = lab_client.patch(
        f"/api/v1/laboratories/{laboratory['lab_id']}/status", json=payload
    )
    assert response.status_code == 422


@pytest.mark.parametrize("environment", ["test", "staging", "production"])
def test_restricted_outside_development(environment) -> None:
    from app.main import create_app

    application = create_app(Settings(_env_file=None, app_env=environment))
    with TestClient(application) as client:
        paths = client.get("/openapi.json").json()["paths"]
        assert not any("laboratories" in path for path in paths)
        for method, path in [
            ("POST", ""), ("GET", ""), ("GET", "/search"),
            ("GET", "/1"), ("PUT", "/1"), ("PATCH", "/1/status"),
        ]:
            assert client.request(
                method, f"/api/v1/laboratories{path}"
            ).status_code == 404


def test_runtime_access_guard(lab_client) -> None:
    lab_client.app.state.settings = Settings(_env_file=None, app_env="production")
    assert lab_client.get("/api/v1/laboratories").status_code == 404


def test_swagger_and_existing_patient_api(lab_client) -> None:
    assert lab_client.get("/docs").status_code == 200
    schema = lab_client.get("/openapi.json").json()
    paths = schema["paths"]
    assert set(paths["/api/v1/laboratories"]) == {"get", "post"}
    assert "patch" in paths["/api/v1/laboratories/{lab_id}/status"]
    assert paths["/api/v1/laboratories"]["post"]["tags"] == ["Laboratories"]
    assert "LaboratoryStatusUpdate" in schema["components"]["schemas"]
    assert "get" in paths["/api/v1/patients"]
    response = lab_client.post("/api/v1/patients", json={
        "full_name": "Synthetic Patient", "phone": "9876543210",
    })
    assert response.status_code == 201
    assert lab_client.get(response.headers["Location"]).status_code == 200


def test_logs_do_not_include_contacts_or_search(lab_client) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("diagnostic")
    logger.addHandler(handler)
    try:
        laboratory = register(
            lab_client, lab_name="Private Laboratory", email="private@example.com",
            phone="9876543210", contact_person="Private Contact",
        )
        lab_client.get(f"/api/v1/laboratories/{laboratory['lab_id']}")
        lab_client.get("/api/v1/laboratories/search", params={"q": "Private"})
    finally:
        logger.removeHandler(handler)
    output = stream.getvalue()
    for value in ("Private", "private@example.com", "9876543210"):
        assert value not in output
    entries = [json.loads(line) for line in output.splitlines()]
    assert any(
        entry.get("path") == "/api/v1/laboratories/{lab_id}" for entry in entries
    )
