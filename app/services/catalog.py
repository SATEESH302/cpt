"""Catalog transactions, eligibility, and Decimal-only pricing comparisons."""

from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import TypeVar

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.models.diagnostic_test import DiagnosticTest
from app.models.lab_test_price import LabTestPrice
from app.models.laboratory import Laboratory
from app.repositories.catalog import CatalogRepository
from app.schemas.catalog import (
    DiagnosticTestCreate, DiagnosticTestPage, DiagnosticTestResponse,
    DiagnosticTestUpdate, LaboratoryTestPriceCreate, LaboratoryTestPricePage,
    LaboratoryTestPriceResponse, PricingComparisonPage, PricingComparisonRow,
)

Record = TypeVar("Record", DiagnosticTest, LabTestPrice)


def pricing_metrics(selling_price: Decimal, lab_cost: Decimal) -> dict:
    if selling_price <= 0 or lab_cost <= 0:
        raise ApplicationError(
            "INVALID_STORED_PRICE", "Stored prices require administrator review.", 409
        )
    with localcontext() as context:
        context.prec = 40
        spread = selling_price - lab_cost
        cents = Decimal("0.01")
        return {
            "gross_spread": spread.quantize(cents, rounding=ROUND_HALF_UP),
            "gross_margin_percentage": (spread / selling_price * Decimal(100)).quantize(
                cents, rounding=ROUND_HALF_UP
            ),
            "markup_percentage": (spread / lab_cost * Decimal(100)).quantize(
                cents, rounding=ROUND_HALF_UP
            ),
            "negative_margin": spread < 0, "requires_review": spread < 0,
        }


class CatalogService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CatalogRepository(session)

    def get_test(
        self, test_id: int, *, include_inactive: bool = False, lock: bool = False
    ) -> DiagnosticTest:
        test = self.repository.get_test(test_id, lock=lock)
        if test is None or (not include_inactive and (
            test.is_active is not True or test.platform_price <= 0
        )):
            raise ApplicationError(
                "DIAGNOSTIC_TEST_NOT_FOUND", "Diagnostic test not found.", 404
            )
        return test

    def get_lab(self, lab_id: int) -> Laboratory:
        lab = self.repository.get_lab(lab_id)
        if lab is None:
            raise ApplicationError("LABORATORY_NOT_FOUND", "Laboratory not found.", 404)
        return lab

    def create_test(self, payload: DiagnosticTestCreate) -> DiagnosticTest:
        if self.repository.code_exists(payload.test_code):
            raise ApplicationError(
                "DUPLICATE_TEST_CODE", "Test code already exists.", 409
            )
        test = DiagnosticTest(**payload.model_dump(), is_active=True)
        self.repository.add(test)
        return self._save(test, "DUPLICATE_TEST_CODE")

    def update_test(
        self, test_id: int, payload: DiagnosticTestUpdate
    ) -> DiagnosticTest:
        test = self.get_test(test_id, include_inactive=True, lock=True)
        changes = payload.model_dump(exclude_unset=True)
        code = changes.get("test_code")
        if code and self.repository.code_exists(code, exclude_id=test_id):
            raise ApplicationError(
                "DUPLICATE_TEST_CODE", "Test code already exists.", 409
            )
        for name, value in changes.items():
            setattr(test, name, value)
        return self._save(test, "DUPLICATE_TEST_CODE")

    def change_test_status(self, test_id: int, is_active: bool) -> DiagnosticTest:
        test = self.get_test(test_id, include_inactive=True, lock=True)
        test.is_active = is_active
        return self._save(test)

    def change_platform_price(self, test_id: int, price: Decimal) -> DiagnosticTest:
        test = self.get_test(test_id, include_inactive=True, lock=True)
        test.platform_price = price
        # This transaction never touches bookings or booking_tests.
        return self._save(test)

    def list_tests(
        self, page: int, page_size: int, search: str | None = None,
        include_inactive: bool = False,
    ) -> DiagnosticTestPage:
        tests, total = self.repository.list_tests(
            page, page_size, search, include_inactive
        )
        return DiagnosticTestPage(
            items=[DiagnosticTestResponse.model_validate(test) for test in tests],
            total=total, page=page, page_size=page_size,
            pages=(total + page_size - 1) // page_size,
        )

    @staticmethod
    def mapping_response(
        mapping: LabTestPrice, lab: Laboratory, test: DiagnosticTest
    ) -> LaboratoryTestPriceResponse:
        return LaboratoryTestPriceResponse(
            lab_test_id=mapping.lab_test_id, lab_id=mapping.lab_id,
            test_id=mapping.test_id, lab_name=lab.lab_name, lab_status=lab.status,
            test_is_active=test.is_active, is_available=mapping.is_available,
            platform_price=test.platform_price, lab_price=mapping.lab_price,
            created_at=mapping.created_at,
        )

    def create_mapping(
        self, payload: LaboratoryTestPriceCreate
    ) -> LaboratoryTestPriceResponse:
        lab = self.get_lab(payload.lab_id)
        test = self.get_test(payload.test_id, include_inactive=True)
        if self.repository.mapping_exists(payload.lab_id, payload.test_id):
            raise ApplicationError(
                "DUPLICATE_LAB_TEST_MAPPING",
                "Laboratory-test mapping already exists.", 409
            )
        mapping = LabTestPrice(**payload.model_dump())
        self.repository.add(mapping)
        self._save(mapping, "DUPLICATE_LAB_TEST_MAPPING")
        return self.mapping_response(mapping, lab, test)

    def update_mapping(
        self, mapping_id: int, *, price: Decimal | None = None,
        is_available: bool | None = None,
    ) -> LaboratoryTestPriceResponse:
        mapping = self.repository.get_mapping(mapping_id, lock=True)
        if mapping is None:
            raise ApplicationError(
                "LAB_TEST_MAPPING_NOT_FOUND", "Laboratory-test mapping not found.", 404
            )
        lab = self.get_lab(mapping.lab_id)
        test = self.get_test(mapping.test_id, include_inactive=True)
        if price is not None:
            mapping.lab_price = price
        if is_available is not None:
            mapping.is_available = is_available
        self._save(mapping)
        return self.mapping_response(mapping, lab, test)

    def list_mappings(
        self, page: int, page_size: int,
        lab_id: int | None = None, test_id: int | None = None,
    ) -> LaboratoryTestPricePage:
        if lab_id is not None:
            self.get_lab(lab_id)
        if test_id is not None:
            self.get_test(test_id, include_inactive=True)
        rows, total = self.repository.list_mappings(page, page_size, lab_id, test_id)
        return LaboratoryTestPricePage(
            items=[self.mapping_response(*row) for row in rows],
            total=total, page=page, page_size=page_size,
            pages=(total + page_size - 1) // page_size,
        )

    def comparison(
        self, test_id: int, page: int, page_size: int
    ) -> PricingComparisonPage:
        test = self.get_test(test_id, include_inactive=True)
        rows, total = self.repository.list_mappings(page, page_size, test_id=test_id)
        items = []
        for mapping, lab, row_test in rows:
            response = self.mapping_response(mapping, lab, row_test)
            items.append(PricingComparisonRow(
                **response.model_dump(exclude={"eligible_for_booking"}),
                **pricing_metrics(test.platform_price, mapping.lab_price),
            ))
        return PricingComparisonPage(
            test=DiagnosticTestResponse.model_validate(test), items=items,
            total=total, page=page, page_size=page_size,
            pages=(total + page_size - 1) // page_size,
        )

    def _save(self, instance: Record, duplicate_code: str | None = None) -> Record:
        try:
            self.session.flush()
            self.session.refresh(instance)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            code = exc.orig.args[0] if exc.orig.args else None
            if duplicate_code and (
                code == 1062 or getattr(exc.orig, "sqlite_errorcode", None) == 2067
            ):
                raise ApplicationError(
                    duplicate_code, "The requested unique entry already exists.", 409
                ) from None
            raise
        except SQLAlchemyError:
            self.session.rollback()
            raise
        return instance
