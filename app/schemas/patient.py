"""Patient inputs follow the existing table's storage constraints."""

from datetime import date, datetime
from typing import Annotated, Self

from pydantic import (
    BaseModel, ConfigDict, Field, StringConstraints,
    field_validator, model_validator,
)

from app.schemas.common import Address, ContactInput, District, Email, Phone

Name = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=150
)]
Gender = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=20
)]
Pincode = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=10
)]


class PatientInput(ContactInput):
    @field_validator("date_of_birth", check_fields=False)
    @classmethod
    def validate_birth_date(cls, value: date | None) -> date | None:
        if value is not None and (value > date.today() or value.year < 1000):
            raise ValueError("Date of birth must be a past or current MySQL DATE.")
        return value


class PatientCreate(PatientInput):
    full_name: Name
    phone: Phone
    email: Email | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None
    address: Address | None = None
    district: District | None = None
    pincode: Pincode | None = None


class PatientUpdate(PatientInput):
    """Omitted fields are preserved; explicit null clears nullable columns."""

    full_name: Name | None = Field(
        default=None, description="Omit to preserve; explicit null is invalid."
    )
    phone: Phone | None = Field(
        default=None, description="Omit to preserve; explicit null is invalid."
    )
    email: Email | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None
    address: Address | None = None
    district: District | None = None
    pincode: Pincode | None = None

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one patient field must be supplied.")
        for name in ("full_name", "phone"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_id: int
    full_name: str
    phone: str
    email: str | None
    date_of_birth: date | None
    gender: str | None
    address: str | None
    district: str | None
    pincode: str | None
    created_at: datetime | None
    updated_at: datetime | None


class PatientPage(BaseModel):
    items: list[PatientResponse]
    total: int
    page: int
    page_size: int
    pages: int
