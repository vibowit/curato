import logging
from typing import Annotated, List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.recommendation import (
    RecommendationRunCreateRequest,
    RecommendationRunRead,
    RecommendationRunSummary,
)
from app.services.recommendations import RecommendationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendation-runs", tags=["recommendations"])


def get_recommendation_service() -> RecommendationService:
    """Dependency injector for RecommendationService."""
    return RecommendationService()


@router.post(
    "",
    response_model=RecommendationRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new recommendation edition",
)
async def create_recommendation_run(
    request: RecommendationRunCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
) -> RecommendationRunRead:
    """Executes recommendation pipeline using active taste profile and TMDB candidates."""
    run = await service.create_recommendation_run(db=db, request=request)
    return service.to_read_schema(run)


@router.get(
    "/{run_id}",
    response_model=RecommendationRunRead,
    summary="Get recommendation run details and items",
)
def get_recommendation_run(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
) -> RecommendationRunRead:
    """Retrieves full details of a recommendation run with all items."""
    run = service.get_run(db=db, run_id=run_id)
    return service.to_read_schema(run)


@router.get(
    "",
    response_model=List[RecommendationRunSummary],
    summary="List recommendation runs",
)
def list_recommendation_runs(
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> List[RecommendationRunSummary]:
    """Lists historical recommendation runs."""
    runs = service.list_runs(db=db, limit=limit, offset=offset)
    return [
        RecommendationRunSummary(
            id=run.id,
            status=run.status,
            created_at=run.created_at,
            profile_version=run.profile_version,
            model_provider=run.model_provider,
            model_name=run.model_name,
            summary=run.summary,
            recommendations_count=len(run.recommendations),
        )
        for run in runs
    ]
