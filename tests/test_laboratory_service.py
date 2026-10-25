"""Unit tests for status rules and database failures without external data."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.endpoints.laboratories import get_laboratory_service
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.models.laboratory import Laboratory
from app.schemas.laboratory import LaboratoryResponse, LaboratoryStatus
from app.services.laboratory import LaboratoryService


@pytest.mark.parametrize("current,target,allowed", [
    ("PENDING", "PENDING", True), ("PENDING", "ACTIVE", True),
    ("PENDING", "INACTIVE", True), ("ACTIVE", "ACTIVE", True),
    ("ACTIVE", "INACTIVE", True), ("ACTIVE", "PENDING", False),
    ("INACTIVE", "INACTIVE", True), ("INACTIVE", "ACTIVE", True),
    ("INACTIVE", "PENDING", False), (None, "ACTIVE", False),
])
def test_transition_matrix(current, target, allowed) -> None:
    session = Mock(spec=Session)
    service = LaboratoryService(session)
    service.repository = Mock()
    laboratory = Laboratory(lab_id=1, lab_name="Unit Lab", status=current)
    service.repository.get.return_value = laboratory
    if allowed:
        result = service.change_status(1, LaboratoryStatus(target))
        assert result.status == target
        assert LaboratoryResponse.model_validate(result).eligible_for_booking == (
            target == "ACTIVE"
        )
        session.commit.assert_called_once()
    else:
        with pytest.raises(ApplicationError) as exc:
            service.change_status(1, LaboratoryStatus(target))
        assert exc.value.status_code == 409
        assert laboratory.status == current
        session.commit.assert_not_called()
    service.repository.get.assert_called_once_with(1, for_update=True)


@pytest.mark.parametrize("failure", ["flush", "refresh", "commit"])
def test_write_failures_roll_back(failure) -> None:
    session = Mock(spec=Session)
    getattr(session, failure).side_effect = OperationalError(
        "private SQL", {}, Exception("private credentials")
    )
    with pytest.raises(OperationalError):
        LaboratoryService(session)._save(Laboratory(lab_name="Unit Lab"))
    session.rollback.assert_called_once()


@pytest.mark.parametrize("exception,status", [
    (OperationalError("private SQL", {}, Exception("private")), 503),
    (IntegrityError("private SQL", {}, Exception("private")), 409),
    (SQLAlchemyError("private"), 500),
])
def test_database_error_responses(exception, status) -> None:
    from app.main import create_app

    service = Mock()
    service.list.side_effect = exception
    application = create_app(Settings(_env_file=None, app_env="development"))
    application.dependency_overrides[get_laboratory_service] = lambda: service
    with TestClient(application) as client:
        response = client.get("/api/v1/laboratories")
    assert response.status_code == status
    assert "private" not in response.text
    assert response.json()["request_id"] == response.headers["x-request-id"]
