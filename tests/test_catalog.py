"""Catalog HTTP/repository integration uses a private, disposable database."""

import io
import logging
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    BigInteger, DefaultClause, Integer, MetaData, String, create_engine, event, text,
)
from sqlalchemy.dialects.mysql import ENUM
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.db.base import Base
from app.db.session import get_db
from app.models.booking import Booking
from app.models.booking_test import BookingTest
from app.models.patient import Patient
from app.repositories.catalog import CatalogRepository

ROOT = "/api/v1/diagnostic-tests"
PRICES = "/api/v1/laboratory-test-prices"


@pytest.fixture
def catalog_database():
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        cloned = table.to_metadata(metadata)
        for column in cloned.columns:
            if column.primary_key:
                column.type = BigInteger().with_variant(Integer, "sqlite")
            if isinstance(column.type, ENUM):
                column.type = String(50)
            if column.server_default and "ON UPDATE" in str(column.server_default.arg):
                column.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))
    metadata.tables["diagnostic_tests"].c.test_code.type = String(50, collation="NOCASE")
    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    finally:
        engine.dispose()


@pytest.fixture
def catalog_client(catalog_database):
    from app.main import create_app

    application = create_app(Settings(_env_file=None, app_env="development"))

    def isolated_db():
        with catalog_database() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise

    application.dependency_overrides[get_db] = isolated_db
    with TestClient(application) as client:
        yield client
    application.dependency_overrides.clear()


def create_test(client, **changes):
    payload = {"test_name": "Blood Count", "test_code": "CBC", "platform_price": "500.00"}
    payload.update(changes)
    response = client.post(ROOT, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def create_lab(client, active=True):
    response = client.post("/api/v1/laboratories", json={"lab_name": "Synthetic Lab"})
    assert response.status_code == 201
    lab = response.json()
    if active:
        assert client.patch(
            f"/api/v1/laboratories/{lab['lab_id']}/status", json={"status": "ACTIVE"}
        ).status_code == 200
    return lab


def create_mapping(client, lab, test_record, **changes):
    payload = {
        "lab_id": lab["lab_id"], "test_id": test_record["test_id"], "lab_price": "300.00",
    }
    payload.update(changes)
    response = client.post(PRICES, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_retrieve_and_default_status(catalog_client):
    record = create_test(catalog_client, test_code=" cbc ")
    assert record["test_code"] == "CBC"
    assert record["is_active"] is True
    assert record["platform_price"] == "500.00"
    assert catalog_client.get(f"{ROOT}/{record['test_id']}").json() == record


def test_duplicate_code(catalog_client):
    create_test(catalog_client)
    response = catalog_client.post(ROOT, json={
        "test_name": "Duplicate", "test_code": "cbc", "platform_price": "99.00",
    })
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_TEST_CODE"


@pytest.mark.parametrize("price", [
    "0", "-0.01", "100000000.00", "1.001", "NaN", "Infinity", None, True, 1.25,
])
def test_invalid_money(catalog_client, price):
    response = catalog_client.post(ROOT, json={
        "test_name": "Invalid", "test_code": "INVALID", "platform_price": price,
    })
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("payload", [
    {}, {"test_name": "Test"},
    {"test_name": " ", "test_code": "CODE", "platform_price": "1"},
    {"test_name": "Test", "test_code": "bad code", "platform_price": "1"},
    {"test_name": "Test", "test_code": "CODE", "platform_price": "1", "is_active": False},
])
def test_invalid_create(catalog_client, payload):
    assert catalog_client.post(ROOT, json=payload).status_code == 422


def test_update_details_and_duplicate_code(catalog_client):
    first = create_test(catalog_client, category="Blood", description="Old description")
    second = create_test(catalog_client, test_code="THYROID")
    path = f"{ROOT}/{first['test_id']}"
    response = catalog_client.put(path, json={"test_name": "Full Blood Count", "description": None})
    assert response.status_code == 200
    assert response.json()["description"] is None
    assert response.json()["category"] == "Blood"
    assert response.json()["platform_price"] == "500.00"
    assert catalog_client.put(path, json={"test_code": second["test_code"]}).status_code == 409


@pytest.mark.parametrize("payload", [{}, {"test_code": None}, {"test_name": None},
                                      {"platform_price": "10"}, {"test_id": 5}])
def test_invalid_update(catalog_client, payload):
    record = create_test(catalog_client)
    assert catalog_client.put(f"{ROOT}/{record['test_id']}", json=payload).status_code == 422


def test_deactivate_and_reactivate(catalog_client):
    record = create_test(catalog_client)
    path = f"{ROOT}/{record['test_id']}"
    assert catalog_client.patch(f"{path}/status", json={"is_active": False}).status_code == 200
    assert catalog_client.get(path).status_code == 404
    assert catalog_client.get(ROOT).json()["total"] == 0
    assert catalog_client.get(path, params={"include_inactive": True}).status_code == 200
    assert catalog_client.get(ROOT, params={"include_inactive": True}).json()["total"] == 1
    assert catalog_client.patch(f"{path}/status", json={"is_active": True}).status_code == 200
    assert catalog_client.get(path).status_code == 200


def test_search_pagination_and_literals(catalog_client):
    first = create_test(catalog_client, category="Hematology")
    second = create_test(catalog_client, test_code="THYROID", category="Hormones")
    page = catalog_client.get(ROOT, params={"page": 2, "page_size": 1}).json()
    assert (page["total"], page["pages"]) == (2, 2)
    assert page["items"][0]["test_id"] == second["test_id"]
    for q in ("CBC", "Hematology"):
        result = catalog_client.get(f"{ROOT}/search", params={"q": q}).json()
        assert result["items"][0]["test_id"] == first["test_id"]
    for q in ("%", "_", "' OR 1=1 --", "unmatched"):
        assert catalog_client.get(f"{ROOT}/search", params={"q": q}).json()["total"] == 0
    assert catalog_client.get(f"{ROOT}/search", params={"q": "Blood"}).json()["total"] == 2


@pytest.mark.parametrize("path", [
    f"{ROOT}/0", f"{ROOT}/9223372036854775808", f"{ROOT}/search?q=",
    f"{ROOT}?page_size=101", f"{ROOT}?page=0",
])
def test_invalid_query(catalog_client, path):
    assert catalog_client.get(path).status_code == 422


def test_missing_test(catalog_client):
    assert catalog_client.get(f"{ROOT}/999").status_code == 404
    assert catalog_client.patch(f"{ROOT}/999/price", json={"platform_price": "1"}).status_code == 404
    assert catalog_client.get(f"{ROOT}/999/pricing-comparison").status_code == 404


def test_mapping_and_cost_update(catalog_client):
    lab = create_lab(catalog_client)
    record = create_test(catalog_client)
    mapping = create_mapping(catalog_client, lab, record)
    assert mapping["eligible_for_booking"] is True
    assert mapping["platform_price"] == "500.00"
    assert mapping["lab_price"] == "300.00"
    response = catalog_client.put(f"{PRICES}/{mapping['lab_test_id']}", json={"lab_price": "325.25"})
    assert response.status_code == 200
    assert response.json()["lab_price"] == "325.25"
    offered = catalog_client.get(f"/api/v1/laboratories/{lab['lab_id']}/tests").json()
    assert offered["total"] == 1
    assert offered["items"][0]["lab_price"] == "325.25"


def test_duplicate_mapping(catalog_client):
    lab = create_lab(catalog_client)
    record = create_test(catalog_client)
    create_mapping(catalog_client, lab, record)
    response = catalog_client.post(PRICES, json={
        "lab_id": lab["lab_id"], "test_id": record["test_id"], "lab_price": "200",
    })
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_LAB_TEST_MAPPING"


@pytest.mark.parametrize("lab_id,test_id", [(999, 1), (1, 999)])
def test_invalid_foreign_keys(catalog_client, lab_id, test_id):
    create_lab(catalog_client)
    create_test(catalog_client)
    response = catalog_client.post(PRICES, json={
        "lab_id": lab_id, "test_id": test_id, "lab_price": "20",
    })
    assert response.status_code == 404
    assert catalog_client.get(PRICES).json()["total"] == 0


@pytest.mark.parametrize("price", ["0", "-1", "1.001", "NaN", 20.5])
def test_invalid_lab_price(catalog_client, price):
    lab = create_lab(catalog_client)
    record = create_test(catalog_client)
    response = catalog_client.post(PRICES, json={
        "lab_id": lab["lab_id"], "test_id": record["test_id"], "lab_price": price,
    })
    assert response.status_code == 422


def test_effective_availability_respects_all_three_flags(catalog_client):
    lab = create_lab(catalog_client, active=False)
    record = create_test(catalog_client)
    mapping = create_mapping(catalog_client, lab, record)
    path = f"{PRICES}/{mapping['lab_test_id']}/availability"
    assert mapping["is_available"] is True
    assert mapping["eligible_for_booking"] is False
    catalog_client.patch(f"/api/v1/laboratories/{lab['lab_id']}/status", json={"status": "ACTIVE"})
    assert catalog_client.patch(path, json={"is_available": True}).json()["eligible_for_booking"] is True
    assert catalog_client.patch(path, json={"is_available": False}).json()["eligible_for_booking"] is False
    catalog_client.patch(f"{ROOT}/{record['test_id']}/status", json={"is_active": False})
    assert catalog_client.patch(path, json={"is_available": True}).json()["eligible_for_booking"] is False


def test_mapping_filters_pagination_and_missing_ids(catalog_client):
    lab = create_lab(catalog_client)
    first = create_test(catalog_client)
    second = create_test(catalog_client, test_code="TWO")
    create_mapping(catalog_client, lab, first)
    mapping = create_mapping(catalog_client, lab, second)
    result = catalog_client.get(PRICES, params={"lab_id": lab["lab_id"], "page_size": 1, "page": 2}).json()
    assert result["total"] == 2
    assert result["items"][0]["lab_test_id"] == mapping["lab_test_id"]
    assert catalog_client.get(PRICES, params={"test_id": first["test_id"]}).json()["total"] == 1
    assert catalog_client.get("/api/v1/laboratories/999/tests").status_code == 404
    assert catalog_client.put(f"{PRICES}/999", json={"lab_price": "10"}).status_code == 404
    assert catalog_client.patch(f"{PRICES}/999/availability", json={"is_available": False}).status_code == 404


def test_comparison_positive_and_negative_margins(catalog_client):
    record = create_test(catalog_client, platform_price="500.00")
    create_mapping(catalog_client, create_lab(catalog_client), record, lab_price="300.00")
    create_mapping(catalog_client, create_lab(catalog_client), record, lab_price="600.00")
    response = catalog_client.get(f"{ROOT}/{record['test_id']}/pricing-comparison")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    first, second = response.json()["items"]
    assert (first["gross_spread"], first["gross_margin_percentage"], first["markup_percentage"]) == (
        "200.00", "40.00", "66.67",
    )
    assert first["requires_review"] is False
    assert (second["gross_spread"], second["gross_margin_percentage"], second["markup_percentage"]) == (
        "-100.00", "-20.00", "-16.67",
    )
    assert second["negative_margin"] is True
    assert second["requires_review"] is True


def test_historical_booking_prices_preserved(catalog_client, catalog_database):
    record = create_test(catalog_client)
    with catalog_database() as session:
        patient = Patient(full_name="Synthetic Patient", phone="9876543210")
        session.add(patient)
        session.flush()
        booking = Booking(
            patient_id=patient.patient_id, booking_date=datetime(2026, 1, 1),
            collection_type="HOME", total_amount=Decimal("500.00"),
        )
        session.add(booking)
        session.flush()
        item = BookingTest(
            booking_id=booking.booking_id, test_id=record["test_id"],
            price_at_booking=Decimal("500.00"),
        )
        session.add(item)
        session.commit()
        booking_id, item_id = booking.booking_id, item.booking_test_id
    response = catalog_client.patch(f"{ROOT}/{record['test_id']}/price", json={"platform_price": "700.25"})
    assert response.status_code == 200
    assert response.json()["platform_price"] == "700.25"
    with catalog_database() as session:
        assert session.get(Booking, booking_id).total_amount == Decimal("500.00")
        assert session.get(BookingTest, item_id).price_at_booking == Decimal("500.00")


@pytest.mark.parametrize("kind", ["code", "mapping"])
def test_duplicate_race_and_recovery(catalog_client, monkeypatch, kind):
    record = create_test(catalog_client)
    if kind == "code":
        monkeypatch.setattr(CatalogRepository, "code_exists", lambda *a, **k: False)
        response = catalog_client.post(ROOT, json={
            "test_name": "Duplicate", "test_code": "CBC", "platform_price": "10",
        })
        expected = "DUPLICATE_TEST_CODE"
    else:
        lab = create_lab(catalog_client)
        create_mapping(catalog_client, lab, record)
        monkeypatch.setattr(CatalogRepository, "mapping_exists", lambda *a, **k: False)
        response = catalog_client.post(PRICES, json={
            "lab_id": lab["lab_id"], "test_id": record["test_id"], "lab_price": "10",
        })
        expected = "DUPLICATE_LAB_TEST_MAPPING"
    assert response.status_code == 409
    assert response.json()["error"]["code"] == expected
    assert catalog_client.get(ROOT).status_code == 200


@pytest.mark.parametrize("environment", ["production", "staging", "test"])
def test_public_contract_and_admin_restrictions(catalog_client, environment):
    from app.main import create_app

    record = create_test(catalog_client)
    create_mapping(catalog_client, create_lab(catalog_client), record)
    application = create_app(Settings(_env_file=None, app_env=environment))
    application.dependency_overrides[get_db] = catalog_client.app.dependency_overrides[get_db]
    with TestClient(application) as client:
        for path in (ROOT, f"{ROOT}/search?q=CBC", f"{ROOT}/{record['test_id']}"):
            response = client.get(path)
            assert response.status_code == 200
            for private in ("lab_price", "gross_spread", "markup_percentage", "lab_name"):
                assert private not in response.text
        schema = client.get("/openapi.json").json()
        assert set(schema["paths"][ROOT]) == {"get"}
        assert "LaboratoryTestPriceResponse" not in schema["components"]["schemas"]
        assert client.get(f"{ROOT}/{record['test_id']}/pricing-comparison").status_code == 404
        assert client.get(PRICES).status_code == 404
        assert client.get("/api/v1/laboratories/1/tests").status_code == 404
        assert client.post(ROOT, json={}).status_code == 405
        assert client.get(ROOT, params={"include_inactive": True}).status_code == 404


def test_runtime_admin_guard(catalog_client):
    catalog_client.app.state.settings = Settings(_env_file=None, app_env="production")
    assert catalog_client.post(ROOT, json={}).status_code == 404
    assert catalog_client.get(PRICES).status_code == 404


def test_swagger_and_log_privacy(catalog_client):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("diagnostic")
    logger.addHandler(handler)
    try:
        record = create_test(catalog_client, test_name="Unlogged Catalog Name")
        catalog_client.get(f"{ROOT}/search", params={"q": "Unlogged Catalog Name"})
        create_mapping(catalog_client, create_lab(catalog_client), record, lab_price="123.45")
    finally:
        logger.removeHandler(handler)
    assert "Unlogged Catalog Name" not in stream.getvalue()
    assert "123.45" not in stream.getvalue()
    assert catalog_client.get("/docs").status_code == 200
    paths = catalog_client.get("/openapi.json").json()["paths"]
    assert "post" in paths[ROOT]
    assert "patch" in paths[f"{ROOT}/{{test_id}}/price"]
    assert "get" in paths[f"{ROOT}/{{test_id}}/pricing-comparison"]


def test_status_price_and_mapping_update_validation(catalog_client):
    record = create_test(catalog_client)
    mapping = create_mapping(catalog_client, create_lab(catalog_client), record)
    path = f"{ROOT}/{record['test_id']}"
    assert catalog_client.patch(
        f"{path}/status", json={"is_active": "false"}
    ).status_code == 422
    assert catalog_client.patch(
        f"{path}/price", json={"platform_price": "0"}
    ).status_code == 422
    mapping_path = f"{PRICES}/{mapping['lab_test_id']}"
    for payload in ({"lab_price": "0"}, {"lab_price": "10", "lab_id": 999}):
        assert catalog_client.put(mapping_path, json=payload).status_code == 422
    assert catalog_client.patch(
        f"{mapping_path}/availability", json={"is_available": "false"}
    ).status_code == 422


def test_comparison_pagination_and_empty(catalog_client):
    record = create_test(catalog_client)
    path = f"{ROOT}/{record['test_id']}/pricing-comparison"
    assert catalog_client.get(path).json()["items"] == []
    create_mapping(catalog_client, create_lab(catalog_client), record)
    second = create_mapping(catalog_client, create_lab(catalog_client), record)
    result = catalog_client.get(path, params={"page": 2, "page_size": 1}).json()
    assert (result["total"], result["pages"]) == (2, 2)
    assert result["items"][0]["lab_test_id"] == second["lab_test_id"]


@pytest.mark.parametrize("price", ["0.01", "99999999.99", 100])
def test_valid_price_boundaries_and_integers(catalog_client, price):
    record = create_test(catalog_client, platform_price=price)
    assert Decimal(record["platform_price"]) == Decimal(str(price))
