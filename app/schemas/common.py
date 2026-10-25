"""Shared contact fields and normalization for local management APIs."""

import re
from typing import Annotated

from pydantic import (
    BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator,
)

Phone = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=7, max_length=20
)]
Email = Annotated[EmailStr, Field(max_length=255)]
Address = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=16000
)]
District = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=100
)]


class ContactInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("email", mode="before", check_fields=False)
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("phone", check_fields=False)
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is not None and (
            not re.fullmatch(r"\+?[0-9 ()-]+", value)
            or not 7 <= len(re.sub(r"[^0-9]", "", value)) <= 15
        ):
            raise ValueError("Phone must contain 7 to 15 digits.")
        return value
