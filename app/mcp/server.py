import logging
from typing import Any, Dict, List, Optional

from mcp.server.mcpserver import MCPServer
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.models.recommendation import RecommendationRun
from app.models.sync import SyncState
from app.schemas.decision import (
    ApproveBatchRequest,
    DecisionBatchRequest,
    SingleDecisionRequest,
)
from app.schemas.recommendation import RecommendationRunCreateRequest
from app.services.decisions import DecisionService
from app.services.recommendations import RecommendationService
from app.services.sync import SyncService
from app.services.taste import TasteService
from app.services.watchlist import WatchlistService

logger = logging.getLogger(__name__)

mcp_server = MCPServer(
    name=settings.MCP_SERVER_NAME,
    instructions=(
        "Personal movie and TV show recommendation assistant powered by Simkl, "
        "TMDB, and taste profiling. Allows browsing recommendations, watching trailers, "
        "recording decisions (accept, reject, seen, later), and pushing approved items to Simkl."
    ),
    version=settings.VERSION,
)


@mcp_server.tool()
async def get_taste_profile() -> Dict[str, Any]:
    """Returns the currently active user taste profile, including top genres,

    themes/motifs, favorite directors/creators, and anti-preferences.
    """
    try:
        with SessionLocal() as db:
            service = TasteService()
            profile = service.get_active_profile(db)
            if not profile:
                return {
                    "status": "no_profile",
                    "message": "Brak aktywnego profilu gustu. Wygeneruj profil najpierw.",
                }

            schema = service.to_read_schema(profile)
            return {
                "status": "active",
                "version": schema.version,
                "created_at": schema.created_at.isoformat() if schema.created_at else None,
                "summary": schema.content.summary,
                "genres": [g.model_dump() for g in schema.content.genres],
                "themes": [t.model_dump() for t in schema.content.themes],
                "directors_or_creators": schema.content.directors_or_creators,
                "anti_preferences": schema.content.anti_preferences,
                "temporary_interests": [
                    ti.model_dump() for ti in schema.content.temporary_interests
                ],
            }
    except Exception as e:
        logger.exception("Error in get_taste_profile: %s", e)
        return {"error": True, "message": str(e), "error_type": type(e).__name__}


@mcp_server.tool()
async def get_library_stats() -> Dict[str, Any]:
    """Returns library statistics including total items in local database,

    breakdown by status (completed, watching, plantowatch), ratings, and last Simkl sync date.
    """
    try:
        with SessionLocal() as db:
            total_movies = (
                db.scalar(
                    select(func.count(MediaItem.id)).where(MediaItem.media_type == "movie")
                )
                or 0
            )
            total_shows = (
                db.scalar(
                    select(func.count(MediaItem.id)).where(MediaItem.media_type == "show")
                )
                or 0
            )

            completed = (
                db.scalar(
                    select(func.count(WatchHistory.id)).where(
                        WatchHistory.status == "completed"
                    )
                )
                or 0
            )
            watching = (
                db.scalar(
                    select(func.count(WatchHistory.id)).where(
                        WatchHistory.status == "watching"
                    )
                )
                or 0
            )
            plantowatch = (
                db.scalar(
                    select(func.count(WatchHistory.id)).where(
                        WatchHistory.status == "plantowatch"
                    )
                )
                or 0
            )

            rated_count = (
                db.scalar(
                    select(func.count(WatchHistory.id)).where(
                        WatchHistory.user_rating.is_not(None)
                    )
                )
                or 0
            )
            avg_rating_val = db.scalar(
                select(func.avg(WatchHistory.user_rating)).where(
                    WatchHistory.user_rating.is_not(None)
                )
            )
            avg_rating = round(float(avg_rating_val), 2) if avg_rating_val else None

            sync_state = db.scalar(select(SyncState).where(SyncState.provider == "simkl"))
            last_sync_iso = (
                sync_state.last_success_at.isoformat()
                if (sync_state and sync_state.last_success_at)
                else None
            )

            return {
                "total_items": total_movies + total_shows,
                "movies": total_movies,
                "shows": total_shows,
                "status_counts": {
                    "completed": completed,
                    "watching": watching,
                    "plantowatch": plantowatch,
                },
                "rated_items_count": rated_count,
                "average_user_rating": avg_rating,
                "last_simkl_sync": last_sync_iso,
            }
    except Exception as e:
        logger.exception("Error in get_library_stats: %s", e)
        return {"error": True, "message": str(e), "error_type": type(e).__name__}


@mcp_server.tool()
async def sync_simkl(full_sync: bool = False) -> Dict[str, Any]:
    """Synchronizes watch history and watchlists from Simkl into the local database."""
    try:
        with SessionLocal() as db:
            service = SyncService(db_session=db)
            res = await service.sync_simkl(
                media_types=["movies", "shows"],
                force_full=full_sync,
            )
            return {
                "success": res.status == "completed",
                "status": res.status,
                "movies_synced": res.movies_added + res.movies_updated,
                "shows_synced": res.shows_added + res.shows_updated,
                "total_synced": res.total_synced,
                "synced_at": res.synced_at.isoformat() if res.synced_at else None,
                "message": res.message,
            }
    except Exception as e:
        logger.exception("Error in sync_simkl: %s", e)
        return {"error": True, "message": str(e), "error_type": type(e).__name__}


@mcp_server.tool()
async def generate_recommendations(
    movie_limit: int = 10,
    show_limit: int = 5,
    language: Optional[str] = None,
    include_wildcards: bool = True,
) -> Dict[str, Any]:
    """Generates a new recommendation edition (movies & shows) based on active profile.

    Supports optional language parameter (e.g. 'pl', 'en') and include_wildcards flag.
    """
    try:
        with SessionLocal() as db:
            service = RecommendationService()
            req = RecommendationRunCreateRequest(
                movie_limit=movie_limit,
                show_limit=show_limit,
                mode="on_demand",
                language=language,
                include_wildcards=include_wildcards,
            )
            run = await service.create_recommendation_run(db=db, request=req)
            schema = service.to_read_schema(run)

            return {
                "success": True,
                "run_id": schema.id,
                "status": schema.status,
                "profile_version": schema.profile_version,
                "created_at": schema.created_at.isoformat() if schema.created_at else None,
                "summary": schema.summary,
                "total_recommendations": len(schema.recommendations),
            }
    except Exception as e:
        logger.exception("Error in generate_recommendations: %s", e)
        return {"error": True, "message": str(e), "error_type": type(e).__name__}


@mcp_server.tool()
async def get_recommendations(run_id: Optional[int] = None) -> Dict[str, Any]:
    """Retrieves recommendations from a specific run, or from the latest run."""
    try:
        with SessionLocal() as db:
            service = RecommendationService()
            if run_id is not None:
                run = service.get_run(db=db, run_id=run_id)
            else:
                run = service.get_latest_run(db=db)
                if not run:
                    return {
                        "status": "no_runs",
                        "message": "Brak wygenerowanych rekomendacji.",
                        "recommendations": [],
                    }

            schema = service.to_read_schema(run)
            items = []
            for r in schema.recommendations:
                items.append(
                    {
                        "recommendation_id": r.id,
                        "title": r.media_item.title if r.media_item else "Unknown",
                        "year": r.media_item.year if r.media_item else None,
                        "media_type": r.media_item.media_type if r.media_item else "movie",
                        "match_score": r.match_score,
                        "confidence": r.confidence,
                        "reason": r.reason,
                        "positive_factors": r.positive_factors,
                        "risks": r.risks,
                        "status": r.status,
                        "is_wildcard": r.is_wildcard,
                        "latest_decision": r.latest_decision,
                        "trailer_url": r.trailer_url
                        or (r.media_item.trailer_url if r.media_item else None),
                        "tmdb_id": r.media_item.tmdb_id if r.media_item else None,
                        "imdb_id": r.media_item.imdb_id if r.media_item else None,
                    }
                )

            return {
                "run_id": schema.id,
                "status": schema.status,
                "created_at": schema.created_at.isoformat() if schema.created_at else None,
                "profile_version": schema.profile_version,
                "summary": schema.summary,
                "recommendations": items,
            }
    except Exception as e:
        logger.exception("Error in get_recommendations: %s", e)
        return {"error": True, "message": str(e), "error_type": type(e).__name__}


@mcp_server.tool()
async def get_trailer(
    recommendation_id: Optional[int] = None,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieves official YouTube trailer for a recommendation or movie/show title.

    Parameters:
    - recommendation_id: Optional recommendation ID (e.g. from get_recommendations)
    - title: Optional title to search if recommendation_id is not known
    """
    try:
        with SessionLocal() as db:
            service = RecommendationService()
            target_rec_id = recommendation_id

            if target_rec_id is None and title:
                query = title.strip().lower()
                latest_run = service.get_latest_run(db)
                if latest_run:
                    for r in latest_run.recommendations:
                        if r.media_item and query in r.media_item.title.lower():
                            target_rec_id = r.id
                            break

            if target_rec_id is None:
                return {
                    "error": True,
                    "message": (
                        "Nie podano ID rekomendacji lub nie znaleziono propozycji po tytule."
                    ),
                }

            trailer_data = await service.get_or_fetch_trailer(db, recommendation_id=target_rec_id)
            return {
                "success": True,
                "recommendation_id": trailer_data.recommendation_id,
                "title": trailer_data.title,
                "year": trailer_data.year,
                "has_official_trailer": trailer_data.trailer_url is not None,
                "trailer_url": trailer_data.trailer_url,
                "fallback_search_url": trailer_data.fallback_search_url,
            }
    except Exception as e:
        logger.exception("Error in get_trailer: %s", e)
        return {"error": True, "message": str(e), "error_type": type(e).__name__}


@mcp_server.tool()
async def record_decision(
    recommendation_id: int, decision: str, note: Optional[str] = None
) -> Dict[str, Any]:
    """Records a user decision on a recommendation.

    Allowed decisions: 'accept', 'reject', 'seen', 'later'.
    """
    decision_clean = decision.strip().lower()
    if decision_clean not in {"accept", "reject", "seen", "later"}:
        return {
            "error": True,
            "message": (
                f"Niepoprawna decyzja '{decision}'. Dozwolone: 'accept', 'reject', 'seen', 'later'."
            ),
        }

    try:
        with SessionLocal() as db:
            service = DecisionService(db_session=db)
            batch_req = DecisionBatchRequest(
                decisions=[
                    SingleDecisionRequest(
                        recommendation_id=recommendation_id,
                        decision=decision_clean,  # type: ignore[arg-type]
                        note=note,
                    )
                ]
            )
            res = service.record_decisions(batch_req)
            db.commit()

            return {
                "success": True,
                "recommendation_id": recommendation_id,
                "decision": decision_clean,
                "processed_count": res.processed_count,
            }
    except Exception as e:
        logger.exception("Error in record_decision: %s", e)
        return {"error": True, "message": str(e), "error_type": type(e).__name__}


@mcp_server.tool()
async def approve_recommendations(recommendation_ids: List[int]) -> Dict[str, Any]:
    """Adds previously accepted recommendations to the user's Simkl Plan to Watch list.

    SAFETY INVARIANT: Only items with user decision 'accept' (status 'accepted') will be added.
    """
    if not recommendation_ids:
        return {"error": True, "message": "Lista recommendation_ids nie może być pusta."}

    try:
        with SessionLocal() as db:
            service = WatchlistService(db_session=db)
            batch_req = ApproveBatchRequest(recommendation_ids=recommendation_ids)
            res = await service.add_approved_recommendations(batch_req)

            return {
                "success": res.added_count > 0 or res.already_added_count > 0,
                "total_requested": res.total_requested,
                "added_count": res.added_count,
                "already_added_count": res.already_added_count,
                "failed_count": res.failed_count,
                "items": [item.model_dump() for item in res.items],
            }
    except Exception as e:
        logger.exception("Error in approve_recommendations: %s", e)
        return {"error": True, "message": str(e), "error_type": type(e).__name__}


@mcp_server.tool()
async def get_recommendation_history(limit: int = 5) -> Dict[str, Any]:
    """Retrieves a list of recent recommendation runs and their status."""
    try:
        with SessionLocal() as db:
            stmt = (
                select(RecommendationRun)
                .order_by(RecommendationRun.created_at.desc())
                .limit(max(1, min(limit, 50)))
            )
            runs = db.scalars(stmt).all()

            history = []
            for r in runs:
                rec_count = len(r.recommendations) if r.recommendations else 0
                accepted_count = sum(
                    1 for rec in (r.recommendations or []) if rec.status in {"accepted", "added"}
                )
                history.append(
                    {
                        "run_id": r.id,
                        "status": r.status,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                        "profile_version": r.profile_version,
                        "summary": r.summary,
                        "total_recommendations": rec_count,
                        "accepted_count": accepted_count,
                    }
                )

            return {
                "total_runs": len(history),
                "runs": history,
            }
    except Exception as e:
        logger.exception("Error in get_recommendation_history: %s", e)
        return {"error": True, "message": str(e), "error_type": type(e).__name__}
