"""Service failure tests mock transactions; they never contact MySQL."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pymysql.err import IntegrityError as MySQLIntegrityError
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.api.v1.endpoints.patients import get_patient_service
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.models.patient import Patient
from app.schemas.patient import PatientCreate
from app.services.patient import PatientService


def test_mysql_duplicate_race_uses_safe_error_and_rolls_back() -> None:
    session = Mock(spec=Session)
    service = PatientService(session)
    service.repository = Mock()
    service.repository.email_exists.return_value = False
    session.flush.side_effect = IntegrityError(
        "private SQL", {}, MySQLIntegrityError(1062, "private email")
    )
    with pytest.raises(ApplicationError) as exc:
        service.register(PatientCreate(
            full_name="Unit Patient", phone="9876543210", email="unit@example.com"
        ))
    assert exc.value.code == "DUPLICATE_EMAIL"
    assert "private" not in str(exc.value)
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


@pytest.mark.parametrize("failure", ["flush", "refresh", "commit"])
def test_write_failure_rolls_back(failure) -> None:
    session = Mock(spec=Session)
    getattr(session, failure).side_effect = OperationalError(
        "private SQL", {}, Exception("private credentials")
    )
    service = PatientService(session)
    service.repository = Mock()
    service.repository.email_exists.return_value = False
    with pytest.raises(OperationalError):
        service.register(PatientCreate(full_name="Unit Patient", phone="9876543210"))
    session.rollback.assert_called_once()


def test_nonduplicate_integrity_error_is_not_mislabeled() -> None:
    session = Mock(spec=Session)
    session.flush.side_effect = IntegrityError(
        "private SQL", {}, MySQLIntegrityError(1048, "not null constraint")
    )
    with pytest.raises(IntegrityError):
        PatientService(session)._save(Patient(email="unit@example.com"))
    session.rollback.assert_called_once()


def test_patient_database_error_response_is_sanitized() -> None:
    from app.main import create_app

    service = Mock()
    service.list.side_effect = OperationalError(
        "SELECT private SQL", {}, Exception("private credentials")
    )
    application = create_app(Settings(_env_file=None, app_env="development"))
    application.dependency_overrides[get_patient_service] = lambda: service
    with TestClient(application) as client:
        response = client.get("/api/v1/patients")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert "private" not in response.text
    assert response.json()["request_id"] == response.headers["x-request-id"]
