"""Patient business rules and explicit write transactions."""

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.models.patient import Patient
from app.repositories.patient import PatientRepository
from app.schemas.patient import (
    PatientCreate, PatientPage, PatientResponse, PatientUpdate,
)


def duplicate_email() -> ApplicationError:
    return ApplicationError("DUPLICATE_EMAIL", "Email is already registered.", 409)


class PatientService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = PatientRepository(session)

    def get(self, patient_id: int) -> Patient:
        patient = self.repository.get(patient_id)
        if patient is None:
            raise ApplicationError("PATIENT_NOT_FOUND", "Patient not found.", 404)
        return patient

    def register(self, payload: PatientCreate) -> Patient:
        if payload.email and self.repository.email_exists(str(payload.email)):
            raise duplicate_email()
        patient = Patient(**payload.model_dump())
        self.repository.add(patient)
        return self._save(patient)

    def update(self, patient_id: int, payload: PatientUpdate) -> Patient:
        patient = self.get(patient_id)
        changes = payload.model_dump(exclude_unset=True)
        email = changes.get("email")
        if email and self.repository.email_exists(str(email), exclude_id=patient_id):
            raise duplicate_email()
        for name, value in changes.items():
            setattr(patient, name, value)
        return self._save(patient)

    def _save(self, patient: Patient) -> Patient:
        has_email = patient.email is not None
        try:
            self.session.flush()
            # Refresh timestamps before commit so refresh errors can roll back.
            self.session.refresh(patient)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            # Email is the only user-controlled unique key. The constraint
            # protects against concurrent registrations or email updates.
            mysql_code = exc.orig.args[0] if exc.orig.args else None
            sqlite_code = getattr(exc.orig, "sqlite_errorcode", None)
            if has_email and (mysql_code == 1062 or sqlite_code == 2067):
                raise duplicate_email() from None
            raise
        except SQLAlchemyError:
            self.session.rollback()
            raise
        return patient

    def list(
        self, page: int, page_size: int, search: str | None = None
    ) -> PatientPage:
        patients, total = self.repository.list(page, page_size, search)
        return PatientPage(
            items=[PatientResponse.model_validate(patient) for patient in patients],
            total=total, page=page, page_size=page_size,
            pages=(total + page_size - 1) // page_size,
        )
