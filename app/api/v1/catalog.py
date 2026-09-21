from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.catalog import CatalogMetadataResponse, CatalogSearchResponse
from app.services import catalog_service

router = APIRouter(prefix="/medications/catalog", tags=["catalog"])


@router.get("", response_model=CatalogSearchResponse)
async def search_catalog(
    search: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CatalogSearchResponse:
    return await catalog_service.search_catalog(db, search, limit, cursor)


@router.get("/metadata", response_model=CatalogMetadataResponse)
async def get_metadata(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CatalogMetadataResponse:
    return await catalog_service.get_metadata(db)
