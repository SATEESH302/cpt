"""Explicit safe authentication inputs and profile projections."""

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.schemas.patient import PatientInput, Name, Gender
from app.schemas.common import Email, Phone

Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]


class RegistrationRequest(PatientInput):
    full_name: Name
    phone: Phone
    email: Email
    password: Password
    gender: Gender | None = None
    date_of_birth: date | None = None
    terms_accepted: Literal[True]

    @field_validator("terms_accepted", mode="before")
    @classmethod
    def strict_acceptance(cls, value):
        if value is not True:
            raise ValueError("Terms acceptance is required.")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


def normalized_phone(value: str) -> str:
    return re.sub(r"[^0-9]", "", value)


class AuthPatient(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    patient_id: int
    full_name: str
    email: str | None
    phone: str
    gender: str | None
    date_of_birth: date | None
    role: Literal["patient"] = "patient"


class SessionResponse(BaseModel):
    user: AuthPatient
    csrf_token: str
    expires_at: str


class CsrfResponse(BaseModel):
    csrf_token: str


class MessageResponse(BaseModel):
    message: str
