import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.models.sync import SyncState
from app.services.sync import SyncService


class DummySimklClient:
    def __init__(self, movies=None, shows=None):
        self.movies = movies or []
        self.shows = shows or []
        self.write_calls_count = 0
        self.get_items_calls = []

    async def get_items(self, media_type: str, date_from=None):
        self.get_items_calls.append({"media_type": media_type, "date_from": date_from})
        if media_type == "movies":
            return self.movies
        elif media_type == "shows":
            return self.shows
        return []


@pytest.mark.asyncio
async def test_sync_service_initial_sync(db_session: Session):
    dummy_movies = [
        {
            "movie": {
                "title": "Interstellar",
                "year": 2014,
                "ids": {"simkl": 1001, "tmdb": 157336, "imdb": "tt0816692"},
            },
            "status": "completed",
            "user_rating": 10,
            "last_watched_at": "2024-01-10T15:30:00Z",
        },
        {
            "movie": {
                "title": "Dune",
                "year": 2021,
                "ids": {"simkl": 1002, "tmdb": 438631, "imdb": "tt1160419"},
            },
            "status": "plantowatch",
            "user_rating": None,
            "last_watched_at": None,
        },
    ]
    dummy_shows = [
        {
            "show": {
                "title": "Severance",
                "year": 2022,
                "ids": {"simkl": 2001, "tmdb": 95396, "imdb": "tt11280740"},
            },
            "status": "watching",
            "user_rating": 9,
            "last_watched_at": "2024-02-01T20:00:00Z",
        }
    ]

    client = DummySimklClient(movies=dummy_movies, shows=dummy_shows)
    service = SyncService(db_session=db_session, simkl_client=client)

    result = await service.sync_simkl(media_types=["movies", "shows"], force_full=True)

    assert result.status == "completed"
    assert result.movies_added == 2
    assert result.shows_added == 1
    assert result.total_synced == 3

    # Verify database records
    items = db_session.scalars(select(MediaItem).order_by(MediaItem.id)).all()
    assert len(items) == 3

    history = db_session.scalars(select(WatchHistory).order_by(WatchHistory.id)).all()
    assert len(history) == 3

    dune = db_session.scalar(select(MediaItem).where(MediaItem.simkl_id == 1002))
    assert dune is not None
    assert dune.title == "Dune"
    assert dune.media_type == "movie"
    assert dune.watch_history[0].status == "plantowatch"

    # Verify sync_state
    sync_state = db_session.scalar(select(SyncState).where(SyncState.provider == "simkl"))
    assert sync_state is not None
    assert sync_state.status == "idle"
    assert sync_state.last_success_at is not None
    assert sync_state.error_summary is None


@pytest.mark.asyncio
async def test_sync_service_incremental_sync(db_session: Session):
    # Setup initial state with one movie
    initial_movies = [
        {
            "movie": {
                "title": "Interstellar",
                "year": 2014,
                "ids": {"simkl": 1001, "tmdb": 157336, "imdb": "tt0816692"},
            },
            "status": "watching",
            "user_rating": None,
        }
    ]
    client = DummySimklClient(movies=initial_movies, shows=[])
    service = SyncService(db_session=db_session, simkl_client=client)
    await service.sync_simkl(media_types=["movies"], force_full=True)

    # Now simulate incremental update: user rated Interstellar 10 and completed it
    updated_movies = [
        {
            "movie": {
                "title": "Interstellar",
                "year": 2014,
                "ids": {"simkl": 1001, "tmdb": 157336, "imdb": "tt0816692"},
            },
            "status": "completed",
            "user_rating": 10,
            "last_watched_at": "2026-05-01T12:00:00Z",
        }
    ]
    client2 = DummySimklClient(movies=updated_movies, shows=[])
    service2 = SyncService(db_session=db_session, simkl_client=client2)
    res2 = await service2.sync_simkl(media_types=["movies"], force_full=False)

    assert res2.movies_added == 0
    assert res2.movies_updated == 1

    # Check that there is still only 1 MediaItem in DB (no duplication)
    media_count = len(db_session.scalars(select(MediaItem)).all())
    assert media_count == 1

    # Check that WatchHistory was updated
    item = db_session.scalar(select(MediaItem).where(MediaItem.simkl_id == 1001))
    assert item is not None
    assert item.watch_history[0].status == "completed"
    assert item.watch_history[0].user_rating == 10.0
