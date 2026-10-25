"""Negotiated laboratory costs are development-only administrator data."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies import (
    Catalog, EntityID, Page, PageSize, require_development,
)
from app.schemas.catalog import (
    AvailabilityUpdate, LaboratoryTestPriceCreate, LaboratoryTestPricePage,
    LaboratoryTestPriceResponse, LaboratoryTestPriceUpdate,
)

router = APIRouter(
    tags=["Laboratory Pricing"], dependencies=[Depends(require_development)],
)
FilterID = Annotated[int | None, Query(gt=0, le=9223372036854775807)]


@router.post(
    "/laboratory-test-prices", response_model=LaboratoryTestPriceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_mapping(
    payload: LaboratoryTestPriceCreate, response: Response, service: Catalog
) -> LaboratoryTestPriceResponse:
    response.headers["Cache-Control"] = "no-store"
    return service.create_mapping(payload)


@router.get("/laboratory-test-prices", response_model=LaboratoryTestPricePage)
def list_mappings(
    response: Response, service: Catalog, page: Page = 1, page_size: PageSize = 20,
    lab_id: FilterID = None, test_id: FilterID = None,
) -> LaboratoryTestPricePage:
    response.headers["Cache-Control"] = "no-store"
    return service.list_mappings(page, page_size, lab_id, test_id)


@router.get("/laboratories/{lab_id}/tests", response_model=LaboratoryTestPricePage)
def laboratory_tests(
    lab_id: EntityID, response: Response, service: Catalog,
    page: Page = 1, page_size: PageSize = 20,
) -> LaboratoryTestPricePage:
    response.headers["Cache-Control"] = "no-store"
    return service.list_mappings(page, page_size, lab_id=lab_id)


@router.put(
    "/laboratory-test-prices/{lab_test_id}", response_model=LaboratoryTestPriceResponse
)
def update_mapping(
    lab_test_id: EntityID, payload: LaboratoryTestPriceUpdate,
    response: Response, service: Catalog,
) -> LaboratoryTestPriceResponse:
    response.headers["Cache-Control"] = "no-store"
    return service.update_mapping(lab_test_id, price=payload.lab_price)


@router.patch(
    "/laboratory-test-prices/{lab_test_id}/availability",
    response_model=LaboratoryTestPriceResponse,
)
def change_availability(
    lab_test_id: EntityID, payload: AvailabilityUpdate,
    response: Response, service: Catalog,
) -> LaboratoryTestPriceResponse:
    response.headers["Cache-Control"] = "no-store"
    return service.update_mapping(lab_test_id, is_available=payload.is_available)
