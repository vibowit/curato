from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.models.sync import SyncState


def seed_history(db: Session):
    sync = SyncState(
        provider="simkl",
        last_success_at=datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc),
        status="success",
    )
    db.add(sync)

    m1 = MediaItem(media_type="movie", title="Sicario", year=2015, simkl_id="501")
    m2 = MediaItem(media_type="show", title="Mindhunter", year=2017, simkl_id="502")
    db.add_all([m1, m2])
    db.flush()

    wh1 = WatchHistory(media_item_id=m1.id, status="completed", user_rating=9.0)
    wh2 = WatchHistory(media_item_id=m2.id, status="completed", user_rating=9.5)
    db.add_all([wh1, wh2])
    db.commit()


def test_get_profile_not_found(app_client: TestClient):
    response = app_client.get("/api/profile")
    assert response.status_code == 404
    data = response.json()
    assert data["error_code"] == "NOT_FOUND"


def test_generate_profile_empty_history(app_client: TestClient):
    response = app_client.post("/api/profile/generate")
    assert response.status_code == 400
    data = response.json()
    assert data["error_code"] == "INVALID_STATE"


def test_generate_and_get_profile_flow(app_client: TestClient, db_session: Session):
    seed_history(db_session)

    mock_llm_output = {
        "summary": "Aficionado of intense, grounded procedural thrillers.",
        "genres": [{"name": "Thriller", "weight": 0.95, "confidence": 0.9}],
        "themes": [{"name": "Investigative Realism", "weight": 0.9, "confidence": 0.85}],
        "directors_or_creators": ["Denis Villeneuve", "David Fincher"],
        "anti_preferences": ["Slapstick", "Formulaic Tropes"],
        "temporary_interests": [],
    }

    with patch(
        "app.integrations.llm.gemini.GeminiLLMClient.generate_structured",
        new=AsyncMock(return_value=mock_llm_output),
    ):
        gen_resp = app_client.post("/api/profile/generate")
        assert gen_resp.status_code == 200
        data = gen_resp.json()
        assert data["version"] == "v1.0-gemini"
        assert data["active"] is True
        assert data["content"]["summary"] == "Aficionado of intense, grounded procedural thrillers."
        assert len(data["content"]["genres"]) == 1
        assert data["content"]["genres"][0]["name"] == "Thriller"

    # Now GET /api/profile should return this active profile
    get_resp = app_client.get("/api/profile")
    assert get_resp.status_code == 200
    assert get_resp.json()["version"] == "v1.0-gemini"

    # GET /api/profile/versions should list 1 version
    versions_resp = app_client.get("/api/profile/versions")
    assert versions_resp.status_code == 200
    versions = versions_resp.json()
    assert len(versions) == 1
    assert versions[0]["version"] == "v1.0-gemini"
    assert versions[0]["active"] is True

    # Adjust profile via PUT /api/profile
    put_resp = app_client.put(
        "/api/profile",
        json={
            "anti_preferences": ["Slapstick", "Formulaic Tropes", "Excessive Animation"],
            "change_note": "Limiting animation as requested",
        },
    )
    assert put_resp.status_code == 200
    adjusted_data = put_resp.json()
    assert adjusted_data["version"] == "v1.1-manual"
    assert adjusted_data["active"] is True
    assert "Excessive Animation" in adjusted_data["content"]["anti_preferences"]

    # Now versions should list 2 versions, with v1.1-manual active
    versions_resp2 = app_client.get("/api/profile/versions")
    versions2 = versions_resp2.json()
    assert len(versions2) == 2
    assert versions2[0]["version"] == "v1.1-manual"
    assert versions2[0]["active"] is True
    assert versions2[1]["version"] == "v1.0-gemini"
    assert versions2[1]["active"] is False

    # Get historical version explicitly
    v1_resp = app_client.get("/api/profile/versions/v1.0-gemini")
    assert v1_resp.status_code == 200
    assert v1_resp.json()["version"] == "v1.0-gemini"

    # Reactivate historical version v1.0-gemini
    act_resp = app_client.post("/api/profile/versions/v1.0-gemini/activate")
    assert act_resp.status_code == 200
    assert act_resp.json()["version"] == "v1.0-gemini"
    assert act_resp.json()["active"] is True

    # Verify active profile is now v1.0-gemini
    active_resp = app_client.get("/api/profile")
    assert active_resp.json()["version"] == "v1.0-gemini"


def test_adjust_profile_not_found(app_client: TestClient):
    response = app_client.put(
        "/api/profile",
        json={"change_note": "No active profile"},
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "NOT_FOUND"


def test_get_version_not_found(app_client: TestClient):
    response = app_client.get("/api/profile/versions/v999.0")
    assert response.status_code == 404
    assert response.json()["error_code"] == "NOT_FOUND"


def test_activate_version_not_found(app_client: TestClient):
    response = app_client.post("/api/profile/versions/v999.0/activate")
    assert response.status_code == 404
    assert response.json()["error_code"] == "NOT_FOUND"
