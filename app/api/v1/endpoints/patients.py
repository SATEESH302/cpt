"""Patient HTTP endpoints available only in local development."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_development
from app.db.session import get_db
from app.schemas.patient import (
    PatientCreate, PatientPage, PatientResponse, PatientUpdate,
)
from app.services.patient import PatientService


def get_patient_service(
    session: Annotated[Session, Depends(get_db)]
) -> PatientService:
    return PatientService(session)


router = APIRouter(
    prefix="/patients", tags=["Patients"],
    dependencies=[Depends(require_development)],
)
Service = Annotated[PatientService, Depends(get_patient_service)]
PatientID = Annotated[int, Path(gt=0, le=9223372036854775807)]
Page = Annotated[int, Query(ge=1, le=1000000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def register_patient(
    payload: PatientCreate, response: Response, request: Request, service: Service
) -> PatientResponse:
    patient = service.register(payload)
    response.headers["Location"] = (
        f"{request.app.state.settings.api_v1_prefix}/patients/{patient.patient_id}"
    )
    response.headers["Cache-Control"] = "no-store"
    return PatientResponse.model_validate(patient)


@router.get("", response_model=PatientPage)
def list_patients(
    response: Response, service: Service, page: Page = 1, page_size: PageSize = 20
) -> PatientPage:
    response.headers["Cache-Control"] = "no-store"
    return service.list(page, page_size)


# Static search must precede /{patient_id} to avoid integer parsing conflicts.
@router.get("/search", response_model=PatientPage)
def search_patients(
    response: Response, service: Service,
    q: Annotated[str, Query(min_length=1, max_length=150, pattern=r"\S")],
    page: Page = 1, page_size: PageSize = 20,
) -> PatientPage:
    response.headers["Cache-Control"] = "no-store"
    return service.list(page, page_size, search=q.strip())


@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient(
    patient_id: PatientID, response: Response, service: Service
) -> PatientResponse:
    response.headers["Cache-Control"] = "no-store"
    return PatientResponse.model_validate(service.get(patient_id))


@router.put("/{patient_id}", response_model=PatientResponse)
def update_patient(
    patient_id: PatientID, payload: PatientUpdate, response: Response,
    service: Service,
) -> PatientResponse:
    response.headers["Cache-Control"] = "no-store"
    return PatientResponse.model_validate(service.update(patient_id, payload))
