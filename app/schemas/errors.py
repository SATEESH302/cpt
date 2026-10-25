"""Common public error contract."""

from typing import Literal

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    success: Literal[False] = False
    error: ErrorDetail
    request_id: str
