import logging
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import NotFoundException
from app.schemas.decision import (
    ApproveBatchRequest,
    ApproveBatchResponse,
    DecisionBatchRequest,
    DecisionBatchResponse,
    UserDecisionRead,
)
from app.schemas.recommendation import RecommendationRunRead, TrailerResponse
from app.services.decisions import DecisionService
from app.services.recommendations import RecommendationService
from app.services.watchlist import WatchlistService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def get_decision_service(db: Annotated[Session, Depends(get_db)]) -> DecisionService:
    """Dependency injector for DecisionService."""
    return DecisionService(db_session=db)


def get_watchlist_service(db: Annotated[Session, Depends(get_db)]) -> WatchlistService:
    """Dependency injector for WatchlistService."""
    return WatchlistService(db_session=db)


def get_recommendation_service() -> RecommendationService:
    """Dependency injector for RecommendationService."""
    return RecommendationService()


@router.post(
    "/decisions",
    response_model=DecisionBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Record user decisions for recommendations",
)
def record_decisions(
    request: DecisionBatchRequest,
    service: Annotated[DecisionService, Depends(get_decision_service)],
) -> DecisionBatchResponse:
    """
    Records user decisions: 'accept', 'reject', 'seen', 'later'.
    Updates the status of recommendations and logs audit history.
    """
    return service.record_decisions(request)


@router.post(
    "/approve",
    response_model=ApproveBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Add approved recommendations to Simkl Plan to Watch",
)
async def approve_recommendations(
    request: ApproveBatchRequest,
    service: Annotated[WatchlistService, Depends(get_watchlist_service)],
) -> ApproveBatchResponse:
    """
    Adds approved recommendations to Simkl watchlist.
    SAFETY INVARIANT: Only items with status 'accepted' will be added to Simkl.
    The operation is idempotent: already added items are skipped.
    """
    return await service.add_approved_recommendations(request.recommendation_ids)


@router.get(
    "/decisions",
    response_model=List[UserDecisionRead],
    summary="List historical user decisions",
)
def list_decisions(
    service: Annotated[DecisionService, Depends(get_decision_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    decision: Annotated[Optional[str], Query(description="Filter by decision type")] = None,
) -> List[UserDecisionRead]:
    """Retrieves audit trail of past user decisions with associated media metadata."""
    return service.list_decisions(limit=limit, offset=offset, decision_filter=decision)


@router.get(
    "/latest",
    response_model=RecommendationRunRead,
    summary="Get latest recommendation run details and items",
)
def get_latest_recommendation_run(
    db: Annotated[Session, Depends(get_db)],
    rec_service: Annotated[RecommendationService, Depends(get_recommendation_service)],
) -> RecommendationRunRead:
    """Retrieves full details of the latest recommendation run."""
    run = rec_service.get_latest_run(db=db)
    if not run:
        raise NotFoundException("No recommendation runs found yet.")
    return rec_service.to_read_schema(run)


@router.get(
    "/{recommendation_id}/trailer",
    response_model=TrailerResponse,
    summary="Get or fetch trailer for recommendation",
)
async def get_recommendation_trailer(
    recommendation_id: int,
    db: Annotated[Session, Depends(get_db)],
    rec_service: Annotated[RecommendationService, Depends(get_recommendation_service)],
) -> TrailerResponse:
    """Retrieves or dynamically fetches the YouTube trailer for a recommendation."""
    return await rec_service.get_or_fetch_trailer(db=db, recommendation_id=recommendation_id)
