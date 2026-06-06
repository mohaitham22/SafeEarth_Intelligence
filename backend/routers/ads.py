from typing import List

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.ad import AdResponse
from services import ad_service

router = APIRouter(prefix="/ads", tags=["ads"])


@router.get("", response_model=List[AdResponse])
async def list_ads(response: Response, db: AsyncSession = Depends(get_db)):
    """Public — active promotional content for the home page (guests).

    Short cache so Studio edits (Phase 10) propagate quickly.
    """
    response.headers["Cache-Control"] = "public, max-age=300"
    return await ad_service.list_active_ads(db)
