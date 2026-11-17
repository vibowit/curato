from typing import Any, Dict, List

from fastapi import APIRouter

from app.services.locale import locale_service

router = APIRouter(prefix="/v1/languages", tags=["Languages"])


@router.get("", response_model=List[Dict[str, str]])
def get_languages() -> List[Dict[str, str]]:
    """Returns list of supported and user-defined languages."""
    return locale_service.list_languages()


@router.get("/{code}", response_model=Dict[str, Any])
def get_language_locale(code: str) -> Dict[str, Any]:
    """Returns UI translations and prompt definitions for a specific language."""
    return locale_service.get_locale(code)
