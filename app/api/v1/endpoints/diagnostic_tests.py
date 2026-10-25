"""Public common-price catalog, with development-only administrative writes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.dependencies import (
    Catalog, CatalogVisibility, EntityID, Page, PageSize, require_development,
)
from app.schemas.catalog import (
    DiagnosticTestCreate, DiagnosticTestPage, DiagnosticTestResponse,
    DiagnosticTestStatus, DiagnosticTestUpdate, PlatformPriceUpdate,
    PricingComparisonPage,
)

public_router = APIRouter(prefix="/diagnostic-tests", tags=["Diagnostic Tests"])
admin_router = APIRouter(
    prefix="/diagnostic-tests", tags=["Catalog Administration"],
    dependencies=[Depends(require_development)],
)


@public_router.get("", response_model=DiagnosticTestPage)
def list_tests(
    visibility: CatalogVisibility, service: Catalog,
    page: Page = 1, page_size: PageSize = 20,
) -> DiagnosticTestPage:
    return service.list_tests(page, page_size, include_inactive=visibility)


@public_router.get("/search", response_model=DiagnosticTestPage)
def search_tests(
    visibility: CatalogVisibility, service: Catalog,
    q: Annotated[str, Query(min_length=1, max_length=200, pattern=r"\S")],
    page: Page = 1, page_size: PageSize = 20,
) -> DiagnosticTestPage:
    return service.list_tests(page, page_size, q.strip(), include_inactive=visibility)


@public_router.get("/{test_id}", response_model=DiagnosticTestResponse)
def get_test(
    test_id: EntityID, visibility: CatalogVisibility, service: Catalog
) -> DiagnosticTestResponse:
    return DiagnosticTestResponse.model_validate(
        service.get_test(test_id, include_inactive=visibility)
    )


@admin_router.post(
    "", response_model=DiagnosticTestResponse, status_code=status.HTTP_201_CREATED
)
def create_test(
    payload: DiagnosticTestCreate, response: Response, request: Request,
    service: Catalog,
) -> DiagnosticTestResponse:
    test = service.create_test(payload)
    response.headers["Location"] = (
        f"{request.app.state.settings.api_v1_prefix}/diagnostic-tests/{test.test_id}"
    )
    return DiagnosticTestResponse.model_validate(test)


@admin_router.put("/{test_id}", response_model=DiagnosticTestResponse)
def update_test(
    test_id: EntityID, payload: DiagnosticTestUpdate, service: Catalog
) -> DiagnosticTestResponse:
    return DiagnosticTestResponse.model_validate(service.update_test(test_id, payload))


@admin_router.patch("/{test_id}/status", response_model=DiagnosticTestResponse)
def change_status(
    test_id: EntityID, payload: DiagnosticTestStatus, service: Catalog
) -> DiagnosticTestResponse:
    return DiagnosticTestResponse.model_validate(
        service.change_test_status(test_id, payload.is_active)
    )


@admin_router.patch("/{test_id}/price", response_model=DiagnosticTestResponse)
def change_price(
    test_id: EntityID, payload: PlatformPriceUpdate, service: Catalog
) -> DiagnosticTestResponse:
    return DiagnosticTestResponse.model_validate(
        service.change_platform_price(test_id, payload.platform_price)
    )


@admin_router.get("/{test_id}/pricing-comparison", response_model=PricingComparisonPage)
def compare_prices(
    test_id: EntityID, response: Response, service: Catalog,
    page: Page = 1, page_size: PageSize = 20,
) -> PricingComparisonPage:
    response.headers["Cache-Control"] = "no-store"
    return service.comparison(test_id, page, page_size)
