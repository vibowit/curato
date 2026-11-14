import logging
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks

from app.core.scheduler import (
    get_scheduler_status,
    run_weekly_recommendation_job,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/status")
def scheduler_status() -> Dict[str, Any]:
    """Returns the current status of the background recommendation scheduler."""
    return get_scheduler_status()


@router.post("/trigger")
async def trigger_scheduler_job(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """Triggers the weekly recommendation generation job on-demand in the background."""
    background_tasks.add_task(run_weekly_recommendation_job)
    return {
        "status": "triggered",
        "message": "Weekly recommendation job has been queued in the background.",
    }
