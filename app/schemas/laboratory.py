"""Laboratory contracts for the existing MySQL schema."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    BaseModel, ConfigDict, Field, StringConstraints, computed_field,
    model_validator,
)

from app.schemas.common import Address, ContactInput, District, Email, Phone

LabName = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=200
)]
ContactPerson = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=150
)]
Pincode = Annotated[str, StringConstraints(
    strip_whitespace=True, pattern=r"^[1-9][0-9]{5}$"
)]
AccreditationNumber = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=100
)]


class LaboratoryStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class LaboratoryCreate(ContactInput):
    lab_name: LabName
    contact_person: ContactPerson | None = None
    phone: Phone | None = None
    email: Email | None = None
    address: Address | None = None
    district: District | None = None
    pincode: Pincode | None = None
    accreditation_number: AccreditationNumber | None = None


class LaboratoryUpdate(ContactInput):
    lab_name: LabName | None = Field(
        default=None, description="Omit to preserve; explicit null is invalid."
    )
    contact_person: ContactPerson | None = None
    phone: Phone | None = None
    email: Email | None = None
    address: Address | None = None
    district: District | None = None
    pincode: Pincode | None = None
    accreditation_number: AccreditationNumber | None = None

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one laboratory field must be supplied.")
        if "lab_name" in self.model_fields_set and self.lab_name is None:
            raise ValueError("lab_name cannot be null.")
        return self


class LaboratoryStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: LaboratoryStatus


class LaboratoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lab_id: int
    lab_name: str
    contact_person: str | None
    phone: str | None
    email: str | None
    address: str | None
    district: str | None
    pincode: str | None
    accreditation_number: str | None
    status: LaboratoryStatus | None
    created_at: datetime | None
    updated_at: datetime | None

    @computed_field
    @property
    def eligible_for_booking(self) -> bool:
        """Status eligibility only; no booking assignment is performed."""
        return self.status == LaboratoryStatus.ACTIVE


class LaboratoryPage(BaseModel):
    items: list[LaboratoryResponse]
    total: int
    page: int
    page_size: int
    pages: int
