from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.schemas.sync import SimklSyncResponse


def test_get_sync_status(app_client: TestClient):
    response = app_client.get("/api/sync/simkl/status")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "simkl"
    assert data["status"] == "idle"


def test_post_sync_simkl(app_client: TestClient):
    mock_resp = SimklSyncResponse(
        status="completed",
        synced_at=datetime.now(timezone.utc),
        movies_added=15,
        movies_updated=2,
        shows_added=5,
        shows_updated=0,
        total_synced=22,
        message="Successfully synced 22 items from Simkl.",
    )

    with patch("app.services.sync.SyncService.sync_simkl", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = mock_resp
        response = app_client.post(
            "/api/sync/simkl",
            json={"media_types": ["movies", "shows"], "force_full": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["movies_added"] == 15
        assert data["total_synced"] == 22


def test_post_sync_simkl_auth_error(app_client: TestClient):
    from app.core.errors import AuthRequiredException

    with patch("app.services.sync.SyncService.sync_simkl", new_callable=AsyncMock) as mock_sync:
        mock_sync.side_effect = AuthRequiredException("Token expired or missing")
        response = app_client.post("/api/sync/simkl")

        assert response.status_code == 401
        data = response.json()
        assert data["error_code"] == "AUTH_REQUIRED"
        assert "Token expired" in data["message"]
