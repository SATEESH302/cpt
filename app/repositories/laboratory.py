"""Bound ORM queries for laboratory management."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.laboratory import Laboratory


class LaboratoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, lab_id: int, *, for_update: bool = False) -> Laboratory | None:
        if for_update:
            # Serialize detail/status changes so transition checks use fresh state.
            return self.session.scalar(
                select(Laboratory).where(Laboratory.lab_id == lab_id)
                .with_for_update().execution_options(populate_existing=True)
            )
        return self.session.get(Laboratory, lab_id)

    def add(self, laboratory: Laboratory) -> None:
        self.session.add(laboratory)

    def list(
        self, page: int, page_size: int, search: str | None = None
    ) -> tuple[list[Laboratory], int]:
        filters = []
        if search is not None:
            filters.append(or_(
                Laboratory.lab_name.contains(search, autoescape=True),
                Laboratory.district.contains(search, autoescape=True),
                Laboratory.pincode.contains(search, autoescape=True),
            ))
        total = self.session.scalar(
            select(func.count()).select_from(Laboratory).where(*filters)
        ) or 0
        query = (
            select(Laboratory).where(*filters).order_by(Laboratory.lab_id)
            .offset((page - 1) * page_size).limit(page_size)
        )
        return list(self.session.scalars(query)), total
