import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.database import SessionLocal
from app.schemas.recommendation import RecommendationRunCreateRequest
from app.services.recommendations import RecommendationService
from app.services.sync import SyncService

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None
_last_job_run: Optional[Dict[str, Any]] = None


async def run_weekly_recommendation_job() -> Dict[str, Any]:
    """Executes the weekly cycle:

    1. Incremental sync with Simkl to update history and watchlists.
    2. Generation of a new recommendation edition (10 movies, 5 shows, mode='weekly').
    """
    global _last_job_run
    start_time = datetime.now(timezone.utc)
    logger.info("Starting scheduled weekly recommendation job at %s", start_time.isoformat())

    result: Dict[str, Any] = {
        "started_at": start_time.isoformat(),
        "status": "running",
        "sync_status": None,
        "run_id": None,
        "error": None,
    }

    try:
        with SessionLocal() as db:
            # 1. Sync Simkl
            sync_service = SyncService(db_session=db)
            sync_res = await sync_service.sync_simkl(
                media_types=["movies", "shows"], force_full=False
            )
            result["sync_status"] = sync_res.status
            logger.info("Scheduled sync completed with status: %s", sync_res.status)

            # 2. Generate Recommendations
            rec_service = RecommendationService()
            req = RecommendationRunCreateRequest(
                movie_limit=10,
                show_limit=5,
                mode="weekly",
            )
            run = await rec_service.create_recommendation_run(db=db, request=req)
            result["run_id"] = run.id
            result["status"] = "completed"
            logger.info(
                "Scheduled recommendation run #%d completed successfully. Summary: %s",
                run.id,
                run.summary,
            )

    except Exception as e:
        logger.exception("Scheduled weekly recommendation job failed: %s", e)
        result["status"] = "failed"
        result["error"] = str(e)

    finally:
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        _last_job_run = result

    return result


def start_scheduler() -> Optional[AsyncIOScheduler]:
    """Starts the AsyncIOScheduler if SCHEDULER_ENABLED is True."""
    global _scheduler
    if not settings.SCHEDULER_ENABLED:
        logger.info("Scheduler is disabled via configuration (SCHEDULER_ENABLED=False).")
        return None

    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler is already running.")
        return _scheduler

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        run_weekly_recommendation_job,
        trigger=IntervalTrigger(hours=settings.SCHEDULER_INTERVAL_HOURS),
        id="weekly_recommendation_job",
        name="Weekly Recommendation Generation",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started. Interval: %d hours. Next run: %s",
        settings.SCHEDULER_INTERVAL_HOURS,
        _scheduler.get_job("weekly_recommendation_job").next_run_time,
    )

    if settings.SCHEDULER_RUN_ON_STARTUP:
        logger.info("SCHEDULER_RUN_ON_STARTUP is True; scheduling immediate execution.")
        asyncio.create_task(run_weekly_recommendation_job())

    return _scheduler


def stop_scheduler() -> None:
    """Shuts down the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down successfully.")
    _scheduler = None


def get_scheduler_status() -> Dict[str, Any]:
    """Returns current scheduler state, job details, and last run summary."""
    is_running = _scheduler is not None and _scheduler.running
    next_run = None
    if is_running:
        job = _scheduler.get_job("weekly_recommendation_job")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

    return {
        "enabled": settings.SCHEDULER_ENABLED,
        "is_running": is_running,
        "interval_hours": settings.SCHEDULER_INTERVAL_HOURS,
        "next_run_time": next_run,
        "last_job_run": _last_job_run,
    }
