"""Register version-one endpoints here as future stories add modules."""

from fastapi import APIRouter

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.patients import router as patients_router
from app.api.v1.endpoints.laboratories import router as laboratories_router
from app.api.v1.endpoints.diagnostic_tests import admin_router as catalog_admin
from app.api.v1.endpoints.diagnostic_tests import public_router as catalog_public
from app.api.v1.endpoints.laboratory_test_prices import router as laboratory_prices


def create_api_router(
    include_patients: bool = False, include_laboratories: bool = False,
    include_catalog_management: bool = False,
) -> APIRouter:
    router = APIRouter()
    router.include_router(health_router)
    router.include_router(auth_router)
    router.include_router(catalog_public)
    if include_catalog_management:
        router.include_router(catalog_admin)
        router.include_router(laboratory_prices)
    if include_patients:
        router.include_router(patients_router)
    if include_laboratories:
        router.include_router(laboratories_router)
    return router
