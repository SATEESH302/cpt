"""Public catalog and private pricing contracts; money serializes as strings."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, Field, StrictBool,
    StringConstraints, computed_field, field_validator, model_validator,
)


def exact_money(value: object) -> object:
    if isinstance(value, (float, bool)):
        raise ValueError("Send money as a decimal string or integer, not a float.")
    return value


Money = Annotated[
    Decimal, BeforeValidator(exact_money, json_schema_input_type=str | int),
    Field(gt=0, max_digits=10, decimal_places=2, allow_inf_nan=False),
]
ID = Annotated[int, Field(gt=0, le=9223372036854775807)]
Name = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=200
)]
Code = Annotated[str, StringConstraints(
    strip_whitespace=True, to_upper=True, min_length=1, max_length=50,
    pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
)]
ShortText = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=100
)]
Description = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=16000
)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("platform_price", "lab_price", check_fields=False)
    @classmethod
    def cents(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))


class DiagnosticTestCreate(Input):
    test_name: Name
    test_code: Code
    platform_price: Money
    category: ShortText | None = None
    description: Description | None = None
    sample_type: ShortText | None = None


class DiagnosticTestUpdate(Input):
    test_name: Name | None = None
    test_code: Code | None = None
    category: ShortText | None = None
    description: Description | None = None
    sample_type: ShortText | None = None

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Supply at least one test detail field.")
        for name in ("test_name", "test_code"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class DiagnosticTestStatus(Input):
    is_active: StrictBool


class PlatformPriceUpdate(Input):
    platform_price: Money


class LaboratoryTestPriceCreate(Input):
    lab_id: ID
    test_id: ID
    lab_price: Money
    is_available: StrictBool = True


class LaboratoryTestPriceUpdate(Input):
    lab_price: Money


class AvailabilityUpdate(Input):
    is_available: StrictBool


class DiagnosticTestResponse(BaseModel):
    """This public contract intentionally contains no negotiated cost fields."""

    model_config = ConfigDict(from_attributes=True)

    test_id: int
    test_name: str
    test_code: str
    category: str | None
    description: str | None
    sample_type: str | None
    platform_price: Decimal
    is_active: bool | None
    created_at: datetime | None


class DiagnosticTestPage(BaseModel):
    items: list[DiagnosticTestResponse]
    total: int
    page: int
    page_size: int
    pages: int


class LaboratoryTestPriceResponse(BaseModel):
    lab_test_id: int
    lab_id: int
    test_id: int
    lab_name: str
    lab_status: str | None
    test_is_active: bool | None
    is_available: bool | None
    platform_price: Decimal
    lab_price: Decimal
    created_at: datetime | None

    @computed_field
    @property
    def eligible_for_booking(self) -> bool:
        return (
            self.lab_status == "ACTIVE" and self.test_is_active is True
            and self.is_available is True
            and self.platform_price > 0 and self.lab_price > 0
        )


class LaboratoryTestPricePage(BaseModel):
    items: list[LaboratoryTestPriceResponse]
    total: int
    page: int
    page_size: int
    pages: int


class PricingComparisonRow(LaboratoryTestPriceResponse):
    gross_spread: Decimal
    gross_margin_percentage: Decimal
    markup_percentage: Decimal
    negative_margin: bool
    requires_review: bool


class PricingComparisonPage(BaseModel):
    test: DiagnosticTestResponse
    items: list[PricingComparisonRow]
    total: int
    page: int
    page_size: int
    pages: int
