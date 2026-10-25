"""Test configuration is independent of process settings and personal .env files."""

import os
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.exceptions import ApplicationError


@pytest.fixture(autouse=True)
def isolated_environment(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[None]:
    if request.node.get_closest_marker("mysql"):
        # Only explicitly opted-in integration tests read local credentials.
        yield
        return
    names = {name.upper() for name in Settings.model_fields}
    for name in list(os.environ):
        if name.upper() in names:
            monkeypatch.delenv(name)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, app_env="test", debug=True)


class TestPayload(BaseModel):
    count: int


@pytest.fixture
def application(settings: Settings) -> FastAPI:
    from app.main import create_app

    application = create_app(settings)

    @application.get("/_test/http")
    async def http_error() -> None:
        raise HTTPException(401, "Authentication required", headers={
            "WWW-Authenticate": "Bearer"
        })

    @application.post("/_test/validation")
    async def validate(payload: TestPayload) -> dict[str, int]:
        return {"count": payload.count}

    @application.get("/_test/unexpected")
    async def unexpected() -> None:
        raise RuntimeError("secret prescription content")

    @application.get("/_test/custom")
    async def custom() -> None:
        raise ApplicationError("RESOURCE_CONFLICT", "Resource already exists.", 409)

    return application


@pytest.fixture
def client(application: FastAPI) -> Iterator[TestClient]:
    with TestClient(application, raise_server_exceptions=False) as client:
        yield client
