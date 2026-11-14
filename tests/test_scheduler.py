from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.scheduler import (
    get_scheduler_status,
    run_weekly_recommendation_job,
    start_scheduler,
    stop_scheduler,
)
from app.main import create_app
from app.schemas.recommendation import RecommendationRunRead
from app.schemas.sync import SimklSyncResponse


def test_scheduler_disabled_by_default(monkeypatch):
    """When SCHEDULER_ENABLED is False, start_scheduler does nothing."""
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", False)
    sched = start_scheduler()
    assert sched is None

    status = get_scheduler_status()
    assert status["enabled"] is False
    assert status["is_running"] is False


@pytest.mark.asyncio
async def test_scheduler_start_and_stop(monkeypatch):
    """When SCHEDULER_ENABLED is True, scheduler starts and stops cleanly."""
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", True)
    sched = start_scheduler()
    assert sched is not None
    assert sched.running is True

    status = get_scheduler_status()
    assert status["enabled"] is True
    assert status["is_running"] is True
    assert status["next_run_time"] is not None

    stop_scheduler()
    status_after = get_scheduler_status()
    assert status_after["is_running"] is False


@pytest.mark.asyncio
async def test_run_weekly_recommendation_job_success():
    """Verifies weekly recommendation job executes sync then generates recommendations."""
    mock_sync = SimklSyncResponse(
        status="completed",
        synced_at=datetime.now(timezone.utc),
        movies_added=2,
        movies_updated=1,
        shows_added=1,
        shows_updated=0,
        total_synced=4,
        message="Synced 4 items",
    )
    mock_run = RecommendationRunRead(
        id=99,
        status="completed",
        created_at=datetime.now(timezone.utc),
        profile_version="v1.0-gemini",
        model_provider="gemini",
        model_name="gemini-2.5-flash",
        summary="Weekly run #99 completed",
        recommendations=[],
    )

    with (
        patch("app.core.scheduler.SyncService") as MockSync,
        patch("app.core.scheduler.RecommendationService") as MockRec,
    ):
        mock_sync_inst = MockSync.return_value
        mock_sync_inst.sync_simkl = AsyncMock(return_value=mock_sync)

        mock_rec_inst = MockRec.return_value
        mock_rec_inst.create_recommendation_run = AsyncMock(return_value=mock_run)

        result = await run_weekly_recommendation_job()

        assert result["status"] == "completed"
        assert result["run_id"] == 99
        assert result["sync_status"] == "completed"
        assert result["error"] is None

        mock_sync_inst.sync_simkl.assert_called_once_with(
            media_types=["movies", "shows"], force_full=False
        )
        assert mock_rec_inst.create_recommendation_run.called


@pytest.mark.asyncio
async def test_run_weekly_recommendation_job_failure():
    """Verifies that failures in the job are caught and recorded in last_job_run."""
    with patch("app.core.scheduler.SyncService") as MockSync:
        mock_sync_inst = MockSync.return_value
        mock_sync_inst.sync_simkl = AsyncMock(side_effect=RuntimeError("Simkl connection error"))

        result = await run_weekly_recommendation_job()

        assert result["status"] == "failed"
        assert "Simkl connection error" in result["error"]

        status = get_scheduler_status()
        assert status["last_job_run"] is not None
        assert status["last_job_run"]["status"] == "failed"


def test_scheduler_api_endpoints():
    """Verifies GET /api/scheduler/status and POST /api/scheduler/trigger."""
    app = create_app()
    with TestClient(app) as client:
        # GET /api/scheduler/status
        res_status = client.get("/api/scheduler/status")
        assert res_status.status_code == 200
        data = res_status.json()
        assert "enabled" in data
        assert "is_running" in data

        # POST /api/scheduler/trigger
        res_trigger = client.post("/api/scheduler/trigger")
        assert res_trigger.status_code == 200
        assert res_trigger.json()["status"] == "triggered"
