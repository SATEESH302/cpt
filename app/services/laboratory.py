"""Laboratory registration, updates, and controlled status transitions."""

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.models.laboratory import Laboratory
from app.repositories.laboratory import LaboratoryRepository
from app.schemas.laboratory import (
    LaboratoryCreate, LaboratoryPage, LaboratoryResponse, LaboratoryStatus,
    LaboratoryUpdate,
)

ALLOWED_TRANSITIONS = {
    LaboratoryStatus.PENDING: {LaboratoryStatus.ACTIVE, LaboratoryStatus.INACTIVE},
    LaboratoryStatus.ACTIVE: {LaboratoryStatus.INACTIVE},
    LaboratoryStatus.INACTIVE: {LaboratoryStatus.ACTIVE},
}


class LaboratoryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = LaboratoryRepository(session)

    def get(self, lab_id: int, *, for_update: bool = False) -> Laboratory:
        laboratory = self.repository.get(lab_id, for_update=for_update)
        if laboratory is None:
            raise ApplicationError(
                "LABORATORY_NOT_FOUND", "Laboratory not found.", 404
            )
        return laboratory

    def register(self, payload: LaboratoryCreate) -> Laboratory:
        laboratory = Laboratory(
            **payload.model_dump(), status=LaboratoryStatus.PENDING.value
        )
        self.repository.add(laboratory)
        return self._save(laboratory)

    def update(self, lab_id: int, payload: LaboratoryUpdate) -> Laboratory:
        laboratory = self.get(lab_id, for_update=True)
        for name, value in payload.model_dump(exclude_unset=True).items():
            setattr(laboratory, name, value)
        return self._save(laboratory)

    def change_status(
        self, lab_id: int, status: LaboratoryStatus
    ) -> Laboratory:
        laboratory = self.get(lab_id, for_update=True)
        current = laboratory.status
        if current != status and status not in ALLOWED_TRANSITIONS.get(current, set()):
            raise ApplicationError(
                "INVALID_LABORATORY_STATUS_TRANSITION",
                "The requested laboratory status transition is not allowed.", 409,
            )
        laboratory.status = status.value
        return self._save(laboratory)

    def _save(self, laboratory: Laboratory) -> Laboratory:
        try:
            self.session.flush()
            self.session.refresh(laboratory)
            self.session.commit()
        except SQLAlchemyError:
            self.session.rollback()
            raise
        return laboratory

    def list(
        self, page: int, page_size: int, search: str | None = None
    ) -> LaboratoryPage:
        laboratories, total = self.repository.list(page, page_size, search)
        return LaboratoryPage(
            items=[LaboratoryResponse.model_validate(lab) for lab in laboratories],
            total=total, page=page, page_size=page_size,
            pages=(total + page_size - 1) // page_size,
        )
