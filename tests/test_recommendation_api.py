from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.taste import TasteProfile
from app.schemas.recommendation import CandidateItem
from app.schemas.taste import TasteProfileContent, WeightedFeature


def seed_active_profile(db: Session):
    content = TasteProfileContent(
        summary="Miłośnik kina neo-noir, thrillerów i dramatów psychologicznych.",
        genres=[
            WeightedFeature(name="Crime", weight=0.9, confidence=0.85),
            WeightedFeature(name="Drama", weight=0.85, confidence=0.8),
        ],
        themes=[
            WeightedFeature(name="Moral ambiguity", weight=0.85, confidence=0.8),
        ],
        directors_or_creators=["Denis Villeneuve", "David Fincher"],
        anti_preferences=["Superbohaterowie", "Animacje dla dzieci"],
        temporary_interests=[],
        metadata={"model": "test"},
    )
    profile = TasteProfile(
        version="v1.0-gemini",
        active=True,
        profile_json=content.model_dump_json(),
    )
    db.add(profile)
    db.commit()


def test_create_run_no_active_profile(app_client: TestClient):
    response = app_client.post(
        "/api/recommendation-runs",
        json={"movie_limit": 10, "show_limit": 5, "mode": "weekly"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["error_code"] == "INVALID_STATE"


def test_create_and_get_recommendation_run(app_client: TestClient, db_session: Session):
    seed_active_profile(db_session)

    mock_candidates = [
        CandidateItem(
            tmdb_id=101,
            media_type="movie",
            title="Prisoners",
            year=2013,
            genres=["Crime", "Drama"],
            director_or_creator="Denis Villeneuve",
            vote_average=8.1,
            overview="A dark thriller.",
            source_strategy="similar_to_favorites",
        ),
        CandidateItem(
            tmdb_id=201,
            media_type="show",
            title="Mindhunter",
            year=2017,
            genres=["Crime", "Drama"],
            director_or_creator="David Fincher",
            vote_average=8.6,
            overview="FBI agents profile serial killers.",
            source_strategy="director",
        ),
    ]

    mock_llm_output = {
        "evaluations": [
            {
                "candidate_index": 0,
                "match_score": 93.0,
                "confidence": 0.9,
                "positive_factors": ["Gęsta atmosfera neo-noir", "Znakomite aktorstwo"],
                "risks": [],
                "reason": "Znakomicie wpisuje się w preferencje mrocznych dramatów proceduralnych.",
            },
            {
                "candidate_index": 1,
                "match_score": 95.0,
                "confidence": 0.92,
                "positive_factors": ["Psychologia kryminalna", "Reżyseria Fincher"],
                "risks": [],
                "reason": "Wzorcowy serial psychologiczno-kryminalny.",
            },
        ]
    }

    with (
        patch(
            "app.services.discovery.DiscoveryService.discover_candidates",
            new=AsyncMock(return_value=mock_candidates),
        ),
        patch(
            "app.integrations.llm.gemini.GeminiLLMClient.generate_structured",
            new=AsyncMock(return_value=mock_llm_output),
        ),
    ):
        res = app_client.post(
            "/api/recommendation-runs",
            json={"movie_limit": 1, "show_limit": 1, "mode": "weekly"},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"
        assert data["profile_version"] == "v1.0-gemini"
        assert len(data["recommendations"]) == 2

        run_id = data["id"]
        rec1 = data["recommendations"][0]
        assert rec1["status"] == "pending"
        assert rec1["match_score"] > 90.0
        assert rec1["media_item"]["title"] in ["Prisoners", "Mindhunter"]

        # Test GET /api/recommendation-runs/{run_id}
        get_res = app_client.get(f"/api/recommendation-runs/{run_id}")
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["id"] == run_id
        assert len(get_data["recommendations"]) == 2

        # Test GET /api/recommendation-runs list
        list_res = app_client.get("/api/recommendation-runs")
        assert list_res.status_code == 200
        list_data = list_res.json()
        assert len(list_data) == 1
        assert list_data[0]["id"] == run_id
        assert list_data[0]["recommendations_count"] == 2


def test_get_recommendation_run_not_found(app_client: TestClient):
    res = app_client.get("/api/recommendation-runs/99999")
    assert res.status_code == 404
    assert res.json()["error_code"] == "NOT_FOUND"
