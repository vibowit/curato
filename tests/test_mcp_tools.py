import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.mcp.server import mcp_server
from app.models.base import Base
from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.models.recommendation import Recommendation, RecommendationRun
from app.models.taste import TasteProfile
from app.schemas.decision import ApproveBatchResponse
from app.schemas.sync import SimklSyncResponse, SimklWriteItemResult


@pytest.fixture(autouse=True)
def setup_mcp_db(tmp_path, monkeypatch):
    """Configures an isolated SQLite database for MCP tests."""
    db_file = tmp_path / "test_mcp.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr("app.mcp.server.SessionLocal", TestingSession)

    yield TestingSession

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.asyncio
async def test_mcp_list_tools():
    """Verifies that all 8 domain tools are registered on the MCP server."""
    tools = await mcp_server.list_tools()
    tool_names = {t.name for t in tools}

    expected = {
        "get_taste_profile",
        "get_library_stats",
        "sync_simkl",
        "generate_recommendations",
        "get_recommendations",
        "record_decision",
        "approve_recommendations",
        "get_recommendation_history",
    }
    assert expected.issubset(tool_names)


@pytest.mark.asyncio
async def test_get_taste_profile_empty():
    """Verifies get_taste_profile when no active profile exists."""
    res = await mcp_server.call_tool("get_taste_profile", {})
    assert not res.is_error
    data = json.loads(res.content[0].text)
    assert data["status"] == "no_profile"


@pytest.mark.asyncio
async def test_get_taste_profile_with_active(setup_mcp_db):
    """Verifies get_taste_profile when an active profile exists."""
    TestingSession = setup_mcp_db
    with TestingSession() as db:
        profile = TasteProfile(
            version="v1.0-gemini",
            active=True,
            profile_json=json.dumps(
                {
                    "summary": "Loves cerebral sci-fi.",
                    "genres": [{"name": "Sci-Fi", "weight": 0.9, "confidence": 0.85}],
                    "themes": [{"name": "AI & Consciousness", "weight": 0.8, "confidence": 0.8}],
                    "directors_or_creators": ["Denis Villeneuve"],
                    "anti_preferences": ["Cheap jumpscares"],
                    "temporary_interests": [],
                    "metadata": {},
                }
            ),
        )
        db.add(profile)
        db.commit()

    res = await mcp_server.call_tool("get_taste_profile", {})
    assert not res.is_error
    data = json.loads(res.content[0].text)
    assert data["status"] == "active"
    assert data["version"] == "v1.0-gemini"
    assert data["genres"][0]["name"] == "Sci-Fi"
    assert "Denis Villeneuve" in data["directors_or_creators"]


@pytest.mark.asyncio
async def test_get_library_stats(setup_mcp_db):
    """Verifies get_library_stats computes accurate database aggregations."""
    TestingSession = setup_mcp_db
    with TestingSession() as db:
        m1 = MediaItem(media_type="movie", title="Blade Runner 2049", year=2017, tmdb_id=335984)
        m2 = MediaItem(media_type="show", title="Severance", year=2022, tmdb_id=93740)
        db.add_all([m1, m2])
        db.flush()

        h1 = WatchHistory(media_item_id=m1.id, status="completed", user_rating=9.5)
        h2 = WatchHistory(media_item_id=m2.id, status="watching", user_rating=None)
        db.add_all([h1, h2])
        db.commit()

    res = await mcp_server.call_tool("get_library_stats", {})
    assert not res.is_error
    data = json.loads(res.content[0].text)

    assert data["total_items"] == 2
    assert data["movies"] == 1
    assert data["shows"] == 1
    assert data["status_counts"]["completed"] == 1
    assert data["status_counts"]["watching"] == 1
    assert data["status_counts"]["plantowatch"] == 0
    assert data["rated_items_count"] == 1
    assert data["average_user_rating"] == 9.5


@pytest.mark.asyncio
async def test_sync_simkl():
    """Verifies sync_simkl delegates to SyncService."""
    from datetime import datetime, timezone

    mock_resp = SimklSyncResponse(
        status="completed",
        synced_at=datetime.now(timezone.utc),
        movies_added=10,
        movies_updated=5,
        shows_added=3,
        shows_updated=2,
        total_synced=20,
        message="Synced 20 items",
    )
    with patch("app.mcp.server.SyncService") as MockSyncService:
        instance = MockSyncService.return_value
        instance.sync_simkl = AsyncMock(return_value=mock_resp)

        res = await mcp_server.call_tool("sync_simkl", {"full_sync": True})
        assert not res.is_error
        data = json.loads(res.content[0].text)
        assert data["success"] is True
        assert data["total_synced"] == 20
        assert data["movies_synced"] == 15
        assert data["shows_synced"] == 5
        instance.sync_simkl.assert_called_once_with(
            media_types=["movies", "shows"], force_full=True
        )


@pytest.mark.asyncio
async def test_generate_recommendations():
    """Verifies generate_recommendations tool invokes RecommendationService."""
    mock_run = MagicMock()
    mock_run.id = 42
    mock_run.status = "completed"
    mock_run.profile_version = "v1.0-gemini"
    mock_run.summary = "Generated 10 movies and 5 shows"
    mock_run.created_at = None
    mock_run.recommendations = []

    with patch("app.mcp.server.RecommendationService") as MockRecService:
        instance = MockRecService.return_value
        instance.create_recommendation_run = AsyncMock(return_value=mock_run)
        instance.to_read_schema.return_value = MagicMock(
            id=42,
            status="completed",
            profile_version="v1.0-gemini",
            created_at=None,
            summary="Generated 10 movies and 5 shows",
            recommendations=[],
        )

        res = await mcp_server.call_tool(
            "generate_recommendations", {"movie_limit": 5, "show_limit": 2}
        )
        assert not res.is_error
        data = json.loads(res.content[0].text)
        assert data["success"] is True
        assert data["run_id"] == 42
        assert data["total_recommendations"] == 0


@pytest.mark.asyncio
async def test_get_recommendations(setup_mcp_db):
    """Verifies get_recommendations tool returns recommendations with metadata."""
    TestingSession = setup_mcp_db
    with TestingSession() as db:
        run = RecommendationRun(
            profile_version="v1.0-gemini",
            model_provider="gemini",
            model_name="gemini-2.5-flash",
            status="completed",
            summary="Edition #1",
        )
        db.add(run)
        db.flush()

        media = MediaItem(media_type="movie", title="Dune", year=2021, tmdb_id=438631)
        db.add(media)
        db.flush()

        rec = Recommendation(
            run_id=run.id,
            media_item_id=media.id,
            match_score=94.0,
            confidence=0.9,
            reason="Masterpiece of sci-fi worldbuilding.",
            status="pending",
        )
        db.add(rec)
        db.commit()

    res = await mcp_server.call_tool("get_recommendations", {})
    assert not res.is_error
    data = json.loads(res.content[0].text)
    assert data["status"] == "completed"
    assert len(data["recommendations"]) == 1
    assert data["recommendations"][0]["title"] == "Dune"
    assert data["recommendations"][0]["match_score"] == 94.0


@pytest.mark.asyncio
async def test_record_decision(setup_mcp_db):
    """Verifies record_decision tool processes valid and invalid decisions."""
    TestingSession = setup_mcp_db
    rec_id = None
    with TestingSession() as db:
        run = RecommendationRun(status="completed", summary="Run")
        media = MediaItem(media_type="movie", title="Arrival", year=2016, tmdb_id=329865)
        db.add_all([run, media])
        db.flush()

        rec = Recommendation(
            run_id=run.id,
            media_item_id=media.id,
            match_score=90.0,
            confidence=0.85,
            reason="Thought-provoking first contact story.",
            status="pending",
        )
        db.add(rec)
        db.commit()
        rec_id = rec.id

    # Test invalid decision
    res_invalid = await mcp_server.call_tool(
        "record_decision", {"recommendation_id": rec_id, "decision": "love_it"}
    )
    data_invalid = json.loads(res_invalid.content[0].text)
    assert data_invalid["error"] is True

    # Test valid decision
    res_valid = await mcp_server.call_tool(
        "record_decision", {"recommendation_id": rec_id, "decision": "accept", "note": "Must watch"}
    )
    assert not res_valid.is_error
    data_valid = json.loads(res_valid.content[0].text)
    assert data_valid["success"] is True
    assert data_valid["decision"] == "accept"


@pytest.mark.asyncio
async def test_approve_recommendations_safeguard():
    """Verifies approve_recommendations passes through WatchlistService and rejects empty lists."""
    # Empty list
    res_empty = await mcp_server.call_tool("approve_recommendations", {"recommendation_ids": []})
    data_empty = json.loads(res_empty.content[0].text)
    assert data_empty["error"] is True

    # Valid call delegating to WatchlistService
    mock_resp = ApproveBatchResponse(
        total_requested=1,
        added_count=1,
        already_added_count=0,
        failed_count=0,
        items=[
            SimklWriteItemResult(
                success=True,
                recommendation_id=10,
                media_type="movie",
                title="Arrival",
                simkl_id=12345,
                tmdb_id=67890,
                status="added",
                message="Added to watchlist",
            )
        ],
    )
    with patch("app.mcp.server.WatchlistService") as MockWatchlistService:
        instance = MockWatchlistService.return_value
        instance.add_approved_recommendations = AsyncMock(return_value=mock_resp)

        res = await mcp_server.call_tool("approve_recommendations", {"recommendation_ids": [10]})
        assert not res.is_error
        data = json.loads(res.content[0].text)
        assert data["success"] is True
        assert data["added_count"] == 1
        assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_get_recommendation_history(setup_mcp_db):
    """Verifies get_recommendation_history retrieves past runs."""
    TestingSession = setup_mcp_db
    with TestingSession() as db:
        r1 = RecommendationRun(status="completed", summary="Run #1", profile_version="v1.0")
        r2 = RecommendationRun(status="completed", summary="Run #2", profile_version="v1.1")
        db.add_all([r1, r2])
        db.commit()

    res = await mcp_server.call_tool("get_recommendation_history", {"limit": 5})
    assert not res.is_error
    data = json.loads(res.content[0].text)
    assert data["total_runs"] == 2
    assert len(data["runs"]) == 2
