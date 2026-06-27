from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import Region, User
from app.schemas.schemas import RegionOut

router = APIRouter(prefix="/regions", tags=["Regions"])


@router.get("", response_model=list[RegionOut])
async def list_regions(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Region).order_by(Region.name))
    return result.scalars().all()