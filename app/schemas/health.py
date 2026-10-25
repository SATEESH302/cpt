"""Public liveness response."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["healthy"] = "healthy"
    service: str
    version: str
