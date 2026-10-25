"""Liveness only: no external resource checks."""

from fastapi import APIRouter, Request

from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        service=settings.service_name, version=settings.app_version
    )
