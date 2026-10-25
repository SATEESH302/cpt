"""Decimal accuracy, eligibility combinations, and safe transaction failures."""

from decimal import Decimal
from itertools import product
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pymysql.err import IntegrityError as MySQLIntegrityError
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_catalog_service
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.models.diagnostic_test import DiagnosticTest
from app.models.lab_test_price import LabTestPrice
from app.schemas.catalog import LaboratoryTestPriceResponse
from app.services.catalog import CatalogService, pricing_metrics


@pytest.mark.parametrize("selling,cost,spread,margin,markup", [
    ("500.00", "300.00", "200.00", "40.00", "66.67"),
    ("500.00", "600.00", "-100.00", "-20.00", "-16.67"),
    ("0.10", "0.03", "0.07", "70.00", "233.33"),
    ("0.03", "0.01", "0.02", "66.67", "200.00"),
    ("20.00", "20.00", "0.00", "0.00", "0.00"),
])
def test_exact_decimal_metrics(selling, cost, spread, margin, markup):
    metrics = pricing_metrics(Decimal(selling), Decimal(cost))
    assert metrics["gross_spread"] == Decimal(spread)
    assert metrics["gross_margin_percentage"] == Decimal(margin)
    assert metrics["markup_percentage"] == Decimal(markup)
    assert metrics["negative_margin"] == (Decimal(cost) > Decimal(selling))
    assert metrics["requires_review"] == metrics["negative_margin"]
    for key in ("gross_spread", "gross_margin_percentage", "markup_percentage"):
        assert isinstance(metrics[key], Decimal)


@pytest.mark.parametrize("selling,cost", [("0", "10"), ("10", "0"), ("-1", "1")])
def test_legacy_invalid_prices_fail_safely(selling, cost):
    with pytest.raises(ApplicationError) as exc:
        pricing_metrics(Decimal(selling), Decimal(cost))
    assert exc.value.code == "INVALID_STORED_PRICE"
    assert exc.value.status_code == 409


@pytest.mark.parametrize("lab_status,test_active,available", list(product(
    ["PENDING", "ACTIVE", "INACTIVE", None], [True, False, None], [True, False, None]
)))
def test_booking_eligibility_matrix(lab_status, test_active, available):
    response = LaboratoryTestPriceResponse(
        lab_test_id=1, lab_id=1, test_id=1, lab_name="Unit Lab",
        lab_status=lab_status, test_is_active=test_active, is_available=available,
        platform_price=Decimal("100"), lab_price=Decimal("50"), created_at=None,
    )
    assert response.eligible_for_booking == (
        lab_status == "ACTIVE" and test_active is True and available is True
    )


@pytest.mark.parametrize("record", [DiagnosticTest, LabTestPrice])
@pytest.mark.parametrize("failure", ["flush", "refresh", "commit"])
def test_write_failures_roll_back(record, failure):
    session = Mock(spec=Session)
    getattr(session, failure).side_effect = OperationalError(
        "private SQL", {}, Exception("private credentials")
    )
    with pytest.raises(OperationalError):
        CatalogService(session)._save(record())
    session.rollback.assert_called_once()


@pytest.mark.parametrize("duplicate_code", ["DUPLICATE_TEST_CODE", "DUPLICATE_LAB_TEST_MAPPING"])
def test_mysql_duplicate_race(duplicate_code):
    session = Mock(spec=Session)
    session.flush.side_effect = IntegrityError(
        "private SQL", {}, MySQLIntegrityError(1062, "private value")
    )
    with pytest.raises(ApplicationError) as exc:
        CatalogService(session)._save(DiagnosticTest(), duplicate_code)
    assert exc.value.code == duplicate_code
    assert "private" not in str(exc.value)
    session.rollback.assert_called_once()


@pytest.mark.parametrize("exception,status", [
    (OperationalError("private SQL", {}, Exception("private cost")), 503),
    (SQLAlchemyError("private credentials"), 500),
])
def test_catalog_database_errors_are_sanitized(exception, status):
    from app.main import create_app

    service = Mock()
    service.list_tests.side_effect = exception
    application = create_app(Settings(_env_file=None, app_env="development"))
    application.dependency_overrides[get_catalog_service] = lambda: service
    with TestClient(application) as client:
        response = client.get("/api/v1/diagnostic-tests")
    assert response.status_code == status
    assert "private" not in response.text
    assert response.json()["request_id"] == response.headers["x-request-id"]
