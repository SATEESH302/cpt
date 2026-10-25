"""Parameterized queries; transaction boundaries belong to services."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.patient import Patient


class PatientRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, patient_id: int) -> Patient | None:
        return self.session.get(Patient, patient_id)

    def email_exists(self, email: str, exclude_id: int | None = None) -> bool:
        query = select(Patient.patient_id).where(Patient.email == email)
        if exclude_id is not None:
            query = query.where(Patient.patient_id != exclude_id)
        return self.session.scalar(query.limit(1)) is not None

    def add(self, patient: Patient) -> None:
        self.session.add(patient)

    def list(
        self, page: int, page_size: int, search: str | None = None
    ) -> tuple[list[Patient], int]:
        filters = []
        if search is not None:
            filters.append(or_(
                Patient.full_name.contains(search, autoescape=True),
                Patient.phone.contains(search, autoescape=True),
            ))
        total = self.session.scalar(
            select(func.count()).select_from(Patient).where(*filters)
        ) or 0
        query = (
            select(Patient).where(*filters).order_by(Patient.patient_id)
            .offset((page - 1) * page_size).limit(page_size)
        )
        return list(self.session.scalars(query)), total
