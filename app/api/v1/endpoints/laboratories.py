"""Local management endpoints; production requires administrator authorization."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_development
from app.db.session import get_db
from app.schemas.laboratory import (
    LaboratoryCreate, LaboratoryPage, LaboratoryResponse,
    LaboratoryStatusUpdate, LaboratoryUpdate,
)
from app.services.laboratory import LaboratoryService


def get_laboratory_service(
    session: Annotated[Session, Depends(get_db)]
) -> LaboratoryService:
    return LaboratoryService(session)


router = APIRouter(
    prefix="/laboratories", tags=["Laboratories"],
    dependencies=[Depends(require_development)],
)
Service = Annotated[LaboratoryService, Depends(get_laboratory_service)]
LabID = Annotated[int, Path(gt=0, le=9223372036854775807)]
Page = Annotated[int, Query(ge=1, le=1000000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.post("", response_model=LaboratoryResponse, status_code=status.HTTP_201_CREATED)
def register_laboratory(
    payload: LaboratoryCreate, request: Request, response: Response,
    service: Service,
) -> LaboratoryResponse:
    laboratory = service.register(payload)
    response.headers["Location"] = (
        f"{request.app.state.settings.api_v1_prefix}/laboratories/{laboratory.lab_id}"
    )
    response.headers["Cache-Control"] = "no-store"
    return LaboratoryResponse.model_validate(laboratory)


@router.get("", response_model=LaboratoryPage)
def list_laboratories(
    response: Response, service: Service, page: Page = 1, page_size: PageSize = 20
) -> LaboratoryPage:
    response.headers["Cache-Control"] = "no-store"
    return service.list(page, page_size)


@router.get("/search", response_model=LaboratoryPage)
def search_laboratories(
    response: Response, service: Service,
    q: Annotated[str, Query(min_length=1, max_length=200, pattern=r"\S")],
    page: Page = 1, page_size: PageSize = 20,
) -> LaboratoryPage:
    response.headers["Cache-Control"] = "no-store"
    return service.list(page, page_size, search=q.strip())


@router.get("/{lab_id}", response_model=LaboratoryResponse)
def get_laboratory(
    lab_id: LabID, response: Response, service: Service
) -> LaboratoryResponse:
    response.headers["Cache-Control"] = "no-store"
    return LaboratoryResponse.model_validate(service.get(lab_id))


@router.put("/{lab_id}", response_model=LaboratoryResponse)
def update_laboratory(
    lab_id: LabID, payload: LaboratoryUpdate, response: Response, service: Service
) -> LaboratoryResponse:
    response.headers["Cache-Control"] = "no-store"
    return LaboratoryResponse.model_validate(service.update(lab_id, payload))


@router.patch("/{lab_id}/status", response_model=LaboratoryResponse)
def change_laboratory_status(
    lab_id: LabID, payload: LaboratoryStatusUpdate, response: Response,
    service: Service,
) -> LaboratoryResponse:
    response.headers["Cache-Control"] = "no-store"
    return LaboratoryResponse.model_validate(
        service.change_status(lab_id, payload.status)
    )
