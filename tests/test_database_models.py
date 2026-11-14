import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.models.recommendation import Recommendation, RecommendationRun, UserDecision
from app.models.settings import AppSetting
from app.models.sync import SyncState


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_create_media_item_and_history(db_session):
    movie = MediaItem(
        media_type="movie",
        title="Dune: Part Two",
        year=2024,
        tmdb_id=693134,
        simkl_id=1849312,
        imdb_id="tt15239678",
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)

    assert movie.id is not None
    assert movie.media_type == "movie"
    assert movie.created_at is not None

    history = WatchHistory(
        media_item_id=movie.id,
        status="completed",
        user_rating=9.5,
    )
    db_session.add(history)
    db_session.commit()

    assert history.id is not None
    assert history.media_item.title == "Dune: Part Two"


def test_recommendation_run_and_uniqueness(db_session):
    movie = MediaItem(media_type="movie", title="Blade Runner 2049", year=2017, tmdb_id=335984)
    db_session.add(movie)
    db_session.commit()

    run = RecommendationRun(status="completed", profile_version="v1.0.0", model_provider="gemini")
    db_session.add(run)
    db_session.commit()

    rec1 = Recommendation(
        run_id=run.id,
        media_item_id=movie.id,
        match_score=0.92,
        confidence=0.88,
        reason="Atmospheric neo-noir sci-fi matching taste profile.",
        status="pending",
    )
    db_session.add(rec1)
    db_session.commit()

    # Verify duplicate recommendation in same run raises IntegrityError
    rec_dup = Recommendation(
        run_id=run.id,
        media_item_id=movie.id,
        match_score=0.90,
        confidence=0.85,
        reason="Duplicate entry",
        status="pending",
    )
    db_session.add(rec_dup)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_user_decision_and_cascade(db_session):
    movie = MediaItem(media_type="show", title="Severance", year=2022, tmdb_id=95396)
    run = RecommendationRun(status="completed")
    db_session.add_all([movie, run])
    db_session.commit()

    rec = Recommendation(
        run_id=run.id,
        media_item_id=movie.id,
        match_score=0.95,
        confidence=0.90,
        reason="Dystopian thriller with dark humor.",
        status="pending",
    )
    db_session.add(rec)
    db_session.commit()

    decision = UserDecision(
        recommendation_id=rec.id,
        decision="accept",
        note="Approved for Simkl Plan to Watch",
    )
    db_session.add(decision)
    db_session.commit()

    assert decision.id is not None
    assert decision.recommendation.media_item.title == "Severance"


def test_sync_state_and_app_settings(db_session):
    state = SyncState(provider="simkl", status="idle")
    db_session.add(state)

    setting = AppSetting(key="weekly_schedule_enabled", value_json="true")
    db_session.add(setting)
    db_session.commit()

    loaded_state = db_session.get(SyncState, "simkl")
    assert loaded_state is not None
    assert loaded_state.status == "idle"

    loaded_setting = db_session.get(AppSetting, "weekly_schedule_enabled")
    assert loaded_setting is not None
    assert loaded_setting.value_json == "true"
