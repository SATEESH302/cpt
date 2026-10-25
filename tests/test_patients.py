"""HTTP/service/repository integration against an isolated SQLite database."""

import io
import json
import logging
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, DefaultClause, Integer, MetaData, String, text
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.db.session import get_db
from app.models.patient import Patient
from app.repositories.patient import PatientRepository


@pytest.fixture
def patient_client():
    from app.main import create_app

    # Clone only into private test metadata. Production mappings stay unchanged.
    metadata = MetaData()
    test_table = Patient.__table__.to_metadata(metadata)
    test_table.c.patient_id.type = BigInteger().with_variant(Integer, "sqlite")
    test_table.c.updated_at.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))
    test_table.c.email.type = String(255, collation="NOCASE")
    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    application = create_app(Settings(_env_file=None, app_env="development"))

    def isolated_db():
        with factory() as session:
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
        engine.dispose()


def register(client: TestClient, **changes) -> dict:
    payload = {"full_name": "Sample Patient", "phone": "+91 98765 43210"}
    payload.update(changes)
    response = client.post("/api/v1/patients", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_registration_and_retrieval(patient_client) -> None:
    response = patient_client.post("/api/v1/patients", json={
        "full_name": "  Sample Patient  ", "phone": "9876543210",
        "email": "Sample.Patient@EXAMPLE.COM", "date_of_birth": "1995-04-12",
        "gender": "female", "address": "Test address", "district": "Test district",
        "pincode": "560001",
    })
    assert response.status_code == 201
    patient = response.json()
    assert patient["patient_id"] > 0
    assert patient["full_name"] == "Sample Patient"
    assert patient["email"] == "sample.patient@example.com"
    assert patient["date_of_birth"] == "1995-04-12"
    assert patient["created_at"] is not None
    assert patient["updated_at"] is not None
    assert response.headers["Location"] == f"/api/v1/patients/{patient['patient_id']}"
    assert response.headers["Cache-Control"] == "no-store"
    assert patient_client.get(response.headers["Location"]).json() == patient


def test_duplicate_email_case_insensitive(patient_client) -> None:
    register(patient_client, email="duplicate@example.com")
    response = patient_client.post("/api/v1/patients", json={
        "full_name": "Another Patient", "phone": "9876543211",
        "email": "DUPLICATE@EXAMPLE.COM",
    })
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_EMAIL"
    assert "duplicate@example.com" not in response.text
    assert patient_client.get("/api/v1/patients").json()["total"] == 1


def test_optional_email_allows_multiple_nulls(patient_client) -> None:
    assert register(patient_client)["email"] is None
    assert register(patient_client)["email"] is None


@pytest.mark.parametrize("payload", [
    {}, {"full_name": "Test"}, {"phone": "9876543210"},
    {"full_name": "  ", "phone": "9876543210"},
    {"full_name": "x" * 151, "phone": "9876543210"},
    {"full_name": "Test", "phone": "letters"},
    {"full_name": "Test", "phone": "123"},
    {"full_name": "Test", "phone": "9876543210", "email": "not-an-email"},
    {"full_name": "Test", "phone": "9876543210", "patient_id": 100},
    {"full_name": "Test", "phone": "9876543210", "date_of_birth": "1000-99-01"},
    {"full_name": "Test", "phone": "9876543210", "pincode": "1" * 11},
    {"full_name": "Test", "phone": "9876543210", "address": "x" * 16001},
])
def test_registration_validation(patient_client, payload) -> None:
    response = patient_client.post("/api/v1/patients", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_future_birth_date_rejected(patient_client) -> None:
    response = patient_client.post("/api/v1/patients", json={
        "full_name": "Test", "phone": "9876543210",
        "date_of_birth": str(date.today() + timedelta(days=1)),
    })
    assert response.status_code == 422


@pytest.mark.parametrize("method,payload", [
    ("get", None), ("put", {"full_name": "New"}),
])
def test_nonexistent_patient(patient_client, method, payload) -> None:
    response = patient_client.request(method, "/api/v1/patients/999", json=payload)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PATIENT_NOT_FOUND"


def test_update_preserves_omitted_and_clears_nullable_fields(patient_client) -> None:
    patient = register(
        patient_client, email="update@example.com", address="Old address"
    )
    path = f"/api/v1/patients/{patient['patient_id']}"
    response = patient_client.put(path, json={
        "full_name": "Updated Name", "email": None, "address": None,
    })
    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated Name"
    assert response.json()["phone"] == patient["phone"]
    assert response.json()["email"] is None
    assert response.json()["address"] is None
    assert patient_client.get(path).json() == response.json()


@pytest.mark.parametrize("payload", [
    {}, {"full_name": None}, {"phone": None}, {"phone": "bad"},
    {"email": "invalid"}, {"created_at": "2020-01-01"},
])
def test_invalid_update(patient_client, payload) -> None:
    patient = register(patient_client)
    response = patient_client.put(
        f"/api/v1/patients/{patient['patient_id']}", json=payload
    )
    assert response.status_code == 422


def test_update_duplicate_email_and_unchanged_email(patient_client) -> None:
    first = register(patient_client, email="first@example.com")
    second = register(patient_client, email="second@example.com")
    path = f"/api/v1/patients/{second['patient_id']}"
    response = patient_client.put(path, json={"email": "SECOND@EXAMPLE.COM"})
    assert response.status_code == 200
    response = patient_client.put(path, json={
        "full_name": "Should not persist", "email": first["email"],
    })
    assert response.status_code == 409
    assert patient_client.get(path).json()["full_name"] == second["full_name"]


def test_pagination(patient_client) -> None:
    ids = [
        register(patient_client, full_name=f"Patient {i}")["patient_id"]
        for i in range(5)
    ]
    first = patient_client.get("/api/v1/patients?page=1&page_size=2").json()
    second = patient_client.get("/api/v1/patients?page=2&page_size=2").json()
    assert (
        first["total"], first["pages"], first["page"], first["page_size"]
    ) == (5, 3, 1, 2)
    assert [item["patient_id"] for item in first["items"]] == ids[:2]
    assert [item["patient_id"] for item in second["items"]] == ids[2:4]
    assert patient_client.get("/api/v1/patients?page=10").json()["items"] == []


def test_empty_list(patient_client) -> None:
    assert patient_client.get("/api/v1/patients").json() == {
        "items": [], "total": 0, "page": 1, "page_size": 20, "pages": 0,
    }


@pytest.mark.parametrize("query", [
    "page=0", "page_size=0", "page_size=101", "page=word",
])
def test_invalid_pagination(patient_client, query) -> None:
    assert patient_client.get(f"/api/v1/patients?{query}").status_code == 422


def test_search_name_phone_and_pagination(patient_client) -> None:
    first = register(patient_client, full_name="Alice Example", phone="9876543201")
    register(patient_client, full_name="Bob Example", phone="9876543202")
    response = patient_client.get("/api/v1/patients/search", params={"q": "alice"})
    assert response.status_code == 200
    assert response.json()["items"][0]["patient_id"] == first["patient_id"]
    assert response.json()["total"] == 1
    response = patient_client.get("/api/v1/patients/search", params={"q": "3202"})
    assert response.json()["items"][0]["full_name"] == "Bob Example"
    response = patient_client.get("/api/v1/patients/search", params={
        "q": "Example", "page_size": 1, "page": 2,
    })
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1
    assert patient_client.get(
        "/api/v1/patients/search", params={"q": "nomatch"}
    ).json()["total"] == 0


@pytest.mark.parametrize("term", ["%", "_", "' OR 1=1 --"])
def test_search_treats_wildcards_and_sql_as_literal(patient_client, term) -> None:
    register(patient_client, full_name="Ordinary Name")
    response = patient_client.get("/api/v1/patients/search", params={"q": term})
    assert response.status_code == 200
    assert response.json()["total"] == 0


@pytest.mark.parametrize("query", [{}, {"q": ""}, {"q": "   "}])
def test_invalid_search(patient_client, query) -> None:
    response = patient_client.get("/api/v1/patients/search", params=query)
    assert response.status_code == 422


def test_duplicate_race_rolls_back_and_session_recovers(
    patient_client, monkeypatch
) -> None:
    register(patient_client, email="race@example.com")
    monkeypatch.setattr(
        PatientRepository, "email_exists", lambda *args, **kwargs: False
    )
    response = patient_client.post("/api/v1/patients", json={
        "full_name": "Race", "phone": "9876543210", "email": "race@example.com",
    })
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_EMAIL"
    register(patient_client, email="after-race@example.com")
    assert patient_client.get("/api/v1/patients").json()["total"] == 2


@pytest.mark.parametrize("environment", ["production", "staging", "test"])
def test_routes_absent_outside_development(environment) -> None:
    from app.main import create_app

    application = create_app(Settings(_env_file=None, app_env=environment))
    with TestClient(application) as client:
        paths = client.get("/openapi.json").json()["paths"]
        assert not any("patients" in path for path in paths)
        for method, path in [
            ("POST", "/api/v1/patients"), ("GET", "/api/v1/patients"),
            ("GET", "/api/v1/patients/1"), ("PUT", "/api/v1/patients/1"),
            ("GET", "/api/v1/patients/search?q=someone"),
        ]:
            assert client.request(method, path).status_code == 404
        assert client.get("/api/v1/health").status_code == 200


def test_patient_swagger_schemas(patient_client) -> None:
    assert patient_client.get("/docs").status_code == 200
    schema = patient_client.get("/openapi.json").json()
    assert schema["paths"]["/api/v1/patients"]["post"]["tags"] == ["Patients"]
    assert "201" in schema["paths"]["/api/v1/patients"]["post"]["responses"]
    assert {
        "PatientCreate", "PatientUpdate", "PatientResponse", "PatientPage"
    } <= set(schema["components"]["schemas"])


def test_patient_information_is_not_logged(patient_client) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("diagnostic")
    logger.addHandler(handler)
    try:
        patient = register(
            patient_client, full_name="Private Person", email="private@example.com"
        )
        patient_client.get(f"/api/v1/patients/{patient['patient_id']}")
        patient_client.get("/api/v1/patients/search", params={"q": "Private Person"})
    finally:
        logger.removeHandler(handler)
    output = stream.getvalue()
    for value in ("Private Person", "private@example.com", "+91 98765 43210"):
        assert value not in output
    entries = [json.loads(line) for line in output.splitlines()]
    assert any(
        entry.get("path") == "/api/v1/patients/{patient_id}" for entry in entries
    )


def test_development_guard_is_checked_at_request_time(patient_client) -> None:
    patient_client.app.state.settings = Settings(
        _env_file=None, app_env="production"
    )
    response = patient_client.get("/api/v1/patients")
    assert response.status_code == 404
