from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.media import MediaItem
from app.models.recommendation import Recommendation, RecommendationRun


def _create_sample_rec(db: Session, status: str = "pending") -> Recommendation:
    media = MediaItem(
        media_type="movie",
        title="Sicario",
        year=2015,
        tmdb_id=273481,
    )
    db.add(media)
    db.flush()

    run = RecommendationRun(
        status="completed",
        profile_version="v1.0-gemini",
        model_provider="gemini",
        model_name="gemini-2.5-flash",
    )
    db.add(run)
    db.flush()

    rec = Recommendation(
        run_id=run.id,
        media_item_id=media.id,
        match_score=94.0,
        confidence=0.9,
        reason="Intense, morally gray border thriller.",
        status=status,
    )
    db.add(rec)
    db.commit()
    return rec


def test_post_decisions_endpoint(app_client: TestClient, db_session: Session):
    rec = _create_sample_rec(db_session, status="pending")

    response = app_client.post(
        "/api/recommendations/decisions",
        json={
            "decisions": [{"recommendation_id": rec.id, "decision": "accept", "note": "Great film"}]
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["processed_count"] == 1
    assert data["decisions"][0]["decision"] == "accept"
    assert data["decisions"][0]["media_title"] == "Sicario"

    # Verify status in database
    db_session.refresh(rec)
    assert rec.status == "accepted"


def test_get_decisions_history_endpoint(app_client: TestClient, db_session: Session):
    rec = _create_sample_rec(db_session, status="pending")
    app_client.post(
        "/api/recommendations/decisions",
        json={"decisions": [{"recommendation_id": rec.id, "decision": "reject"}]},
    )

    response = app_client.get("/api/recommendations/decisions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(d["recommendation_id"] == rec.id and d["decision"] == "reject" for d in data)


def test_get_latest_recommendation_run_endpoint(app_client: TestClient, db_session: Session):
    rec = _create_sample_rec(db_session, status="accepted")

    response = app_client.get("/api/recommendations/latest")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == rec.run_id
    assert len(data["recommendations"]) >= 1
    assert data["recommendations"][0]["id"] == rec.id
    assert data["recommendations"][0]["status"] == "accepted"


@patch("app.integrations.simkl.SimklClient.add_to_list", new_callable=AsyncMock)
def test_post_approve_endpoint(mock_add_to_list, app_client: TestClient, db_session: Session):
    rec = _create_sample_rec(db_session, status="accepted")
    mock_add_to_list.return_value = {"added": {"movies": 1}, "not_found": {"movies": []}}

    response = app_client.post(
        "/api/recommendations/approve",
        json={"recommendation_ids": [rec.id]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_requested"] == 1
    assert data["added_count"] == 1
    assert data["failed_count"] == 0
    assert data["items"][0]["status"] == "added"

    db_session.refresh(rec)
    assert rec.status == "added"


def test_frontend_index_served(app_client: TestClient):
    response = app_client.get("/")
    assert response.status_code == 200
    assert "Simkl Recommender" in response.text
