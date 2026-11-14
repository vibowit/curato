from typing import Annotated, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.sync import (
    SimklSyncRequest,
    SimklSyncResponse,
    SimklSyncStatusResponse,
)
from app.services.sync import SyncService

router = APIRouter(prefix="/sync", tags=["synchronization"])


@router.post("/simkl", response_model=SimklSyncResponse)
async def trigger_simkl_sync(
    db: Annotated[Session, Depends(get_db)],
    request: Optional[SimklSyncRequest] = None,
) -> SimklSyncResponse:
    """
    Triggers synchronization of watch history and watchlists from Simkl into SQLite.
    Supports incremental and full sync options.
    """
    service = SyncService(db_session=db)
    media_types = request.media_types if request else ["movies", "shows"]
    force_full = request.force_full if request else False

    return await service.sync_simkl(media_types=media_types, force_full=force_full)


@router.get("/simkl/status", response_model=SimklSyncStatusResponse)
async def get_simkl_sync_status(
    db: Annotated[Session, Depends(get_db)],
) -> SimklSyncStatusResponse:
    """Retrieves current synchronization state for the Simkl provider."""
    service = SyncService(db_session=db)
    return service.get_status()
