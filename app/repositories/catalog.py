"""Bound catalog and negotiated-price queries; no booking writes."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.diagnostic_test import DiagnosticTest
from app.models.lab_test_price import LabTestPrice
from app.models.laboratory import Laboratory


class CatalogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_test(self, test_id: int, *, lock: bool = False) -> DiagnosticTest | None:
        query = select(DiagnosticTest).where(DiagnosticTest.test_id == test_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(query)

    def get_lab(self, lab_id: int) -> Laboratory | None:
        return self.session.get(Laboratory, lab_id)

    def code_exists(self, code: str, exclude_id: int | None = None) -> bool:
        query = select(DiagnosticTest.test_id).where(DiagnosticTest.test_code == code)
        if exclude_id is not None:
            query = query.where(DiagnosticTest.test_id != exclude_id)
        return self.session.scalar(query.limit(1)) is not None

    def add(self, instance: DiagnosticTest | LabTestPrice) -> None:
        self.session.add(instance)

    def list_tests(
        self, page: int, page_size: int, search: str | None = None,
        include_inactive: bool = False,
    ) -> tuple[list[DiagnosticTest], int]:
        filters = []
        if not include_inactive:
            filters.extend([
                DiagnosticTest.is_active.is_(True), DiagnosticTest.platform_price > 0,
            ])
        if search is not None:
            filters.append(or_(
                DiagnosticTest.test_name.contains(search, autoescape=True),
                DiagnosticTest.test_code.contains(search, autoescape=True),
                DiagnosticTest.category.contains(search, autoescape=True),
            ))
        total = self.session.scalar(
            select(func.count()).select_from(DiagnosticTest).where(*filters)
        ) or 0
        query = (
            select(DiagnosticTest).where(*filters).order_by(DiagnosticTest.test_id)
            .offset((page - 1) * page_size).limit(page_size)
        )
        return list(self.session.scalars(query)), total

    def mapping_exists(self, lab_id: int, test_id: int) -> bool:
        return self.session.scalar(select(LabTestPrice.lab_test_id).where(
            LabTestPrice.lab_id == lab_id, LabTestPrice.test_id == test_id
        ).limit(1)) is not None

    def get_mapping(
        self, mapping_id: int, *, lock: bool = False
    ) -> LabTestPrice | None:
        query = select(LabTestPrice).where(LabTestPrice.lab_test_id == mapping_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(query)

    def list_mappings(
        self, page: int, page_size: int,
        lab_id: int | None = None, test_id: int | None = None,
    ) -> tuple[list[tuple[LabTestPrice, Laboratory, DiagnosticTest]], int]:
        filters = []
        if lab_id is not None:
            filters.append(LabTestPrice.lab_id == lab_id)
        if test_id is not None:
            filters.append(LabTestPrice.test_id == test_id)
        total = self.session.scalar(
            select(func.count()).select_from(LabTestPrice).where(*filters)
        ) or 0
        query = (
            select(LabTestPrice, Laboratory, DiagnosticTest)
            .join(Laboratory, Laboratory.lab_id == LabTestPrice.lab_id)
            .join(DiagnosticTest, DiagnosticTest.test_id == LabTestPrice.test_id)
            .where(*filters).order_by(LabTestPrice.lab_test_id)
            .offset((page - 1) * page_size).limit(page_size)
        )
        return [tuple(row) for row in self.session.execute(query)], total
