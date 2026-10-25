"""Access restrictions shared by management APIs awaiting authentication."""

from typing import Annotated

from fastapi import Depends, Path, Query, Request
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.db.session import get_db
from app.services.catalog import CatalogService

EntityID = Annotated[int, Path(gt=0, le=9223372036854775807)]
Page = Annotated[int, Query(ge=1, le=1000000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def require_development(request: Request) -> None:
    if request.app.state.settings.app_env != "development":
        raise ApplicationError("NOT_FOUND", "Not Found", 404)


def get_catalog_service(
    session: Annotated[Session, Depends(get_db)]
) -> CatalogService:
    return CatalogService(session)


Catalog = Annotated[CatalogService, Depends(get_catalog_service)]


def catalog_visibility(request: Request, include_inactive: bool = False) -> bool:
    if include_inactive:
        require_development(request)
    return include_inactive


CatalogVisibility = Annotated[bool, Depends(catalog_visibility)]
