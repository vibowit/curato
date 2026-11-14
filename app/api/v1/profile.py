from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import NotFoundException
from app.schemas.taste import (
    TasteProfileGenerateRequest,
    TasteProfileRead,
    TasteProfileUpdate,
    TasteProfileVersionSummary,
)
from app.services.taste import TasteService

router = APIRouter(prefix="/profile", tags=["taste-profile"])


@router.get("", response_model=TasteProfileRead)
def get_active_profile(
    db: Annotated[Session, Depends(get_db)],
) -> TasteProfileRead:
    """Returns the currently active taste profile and its version."""
    service = TasteService()
    profile = service.get_active_profile(db)
    if not profile:
        raise NotFoundException(
            message="Nie znaleziono aktywnego profilu gustu. Wygeneruj najpierw profil.",
            details={"provider": "gemini"},
        )
    return service.to_read_schema(profile)


@router.post("/generate", response_model=TasteProfileRead)
async def generate_profile(
    db: Annotated[Session, Depends(get_db)],
    request: Optional[TasteProfileGenerateRequest] = None,
) -> TasteProfileRead:
    """Analyzes watch history and generates a new taste profile version using LLM."""
    service = TasteService()
    profile = await service.generate_profile(db, request=request)
    return service.to_read_schema(profile)


@router.get("/versions", response_model=List[TasteProfileVersionSummary])
def list_profile_versions(
    db: Annotated[Session, Depends(get_db)],
) -> List[TasteProfileVersionSummary]:
    """Lists all stored profile versions with provenance timestamps and active flags."""
    service = TasteService()
    return service.list_profile_versions(db)


@router.get("/versions/{version}", response_model=TasteProfileRead)
def get_profile_version(
    version: str,
    db: Annotated[Session, Depends(get_db)],
) -> TasteProfileRead:
    """Retrieves a specific version of the taste profile."""
    service = TasteService()
    profile = service.get_profile_by_version(db, version)
    return service.to_read_schema(profile)


@router.put("", response_model=TasteProfileRead)
def adjust_active_profile(
    update: TasteProfileUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> TasteProfileRead:
    """Applies manual user adjustments to the active profile, creating a new version."""
    service = TasteService()
    profile = service.adjust_profile(db, update)
    return service.to_read_schema(profile)


@router.post("/versions/{version}/activate", response_model=TasteProfileRead)
def activate_profile_version(
    version: str,
    db: Annotated[Session, Depends(get_db)],
) -> TasteProfileRead:
    """Activates a historical profile version and deactivates the previous active one."""
    service = TasteService()
    profile = service.activate_version(db, version)
    return service.to_read_schema(profile)
