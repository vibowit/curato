import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.integrations.tmdb import TMDBClient
from app.models.base import Base
from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.schemas.taste import TasteProfileContent, WeightedFeature
from app.services.discovery import DiscoveryService


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


@pytest.mark.asyncio
async def test_get_favorites_from_db_balanced(test_db: Session):
    # Add 6 movies and 3 shows with high ratings
    for i in range(1, 7):
        m = MediaItem(media_type="movie", title=f"Top Movie {i}", year=2020 + i, tmdb_id=100 + i)
        test_db.add(m)
        test_db.flush()
        w = WatchHistory(media_item_id=m.id, status="completed", user_rating=10.0)
        test_db.add(w)

    for i in range(1, 4):
        s = MediaItem(media_type="show", title=f"Top Show {i}", year=2015 + i, tmdb_id=200 + i)
        test_db.add(s)
        test_db.flush()
        w = WatchHistory(media_item_id=s.id, status="completed", user_rating=9.5)
        test_db.add(w)

    test_db.commit()

    service = DiscoveryService()
    # Requesting limit=6 should balance 3 movies and 3 shows (not 6 movies)
    favs = await service.get_favorites_from_db(test_db, limit=6)
    assert len(favs) == 6
    movies = [f for f in favs if f.media_type == "movie"]
    shows = [f for f in favs if f.media_type == "show"]
    assert len(movies) == 3
    assert len(shows) == 3

    # Test backfill: when shows are fewer than allocated
    # Request limit=10 targets 5 movies and 5 shows, but only 3 shows exist -> backfills
    favs_backfilled = await service.get_favorites_from_db(test_db, limit=10)
    assert len(favs_backfilled) == 9
    assert len([f for f in favs_backfilled if f.media_type == "show"]) == 3
    assert len([f for f in favs_backfilled if f.media_type == "movie"]) == 6


@pytest.mark.asyncio
async def test_discover_candidates_creator_movies_and_shows(test_db: Session):
    # Setup mock TMDB handler that handles search/person, discover/movie, and person/{id}/tv_credits
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/search/person" in path:
            return httpx.Response(200, json={"results": [{"id": 7467, "name": "David Fincher"}]})
        elif "/discover/movie" in path:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 550,
                            "title": "Fight Club",
                            "release_date": "1999-10-15",
                            "overview": "An insomniac office worker...",
                            "genre_ids": [18, 53],
                            "vote_average": 8.4,
                            "vote_count": 25000,
                            "popularity": 70.0,
                        }
                    ]
                },
            )
        elif "/person/7467/tv_credits" in path:
            return httpx.Response(
                200,
                json={
                    "id": 7467,
                    "crew": [
                        {
                            "id": 82856,
                            "name": "Mindhunter",
                            "first_air_date": "2017-10-13",
                            "overview": "FBI agents interview serial killers...",
                            "genre_ids": [18, 80],
                            "job": "Executive Producer",
                            "department": "Production",
                            "vote_average": 8.1,
                            "vote_count": 2100,
                            "popularity": 55.0,
                        }
                    ],
                },
            )
        elif "/discover/tv" in path:
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json={"results": []})

    transport = httpx.MockTransport(handler)
    client = TMDBClient(api_key="test_key", transport=transport)
    service = DiscoveryService(tmdb_client=client)

    profile = TasteProfileContent(
        summary="Kryminały i thrillery psychologiczne",
        genres=[],
        themes=[],
        directors_or_creators=["David Fincher"],
        anti_preferences=[],
        temporary_interests=[],
        metadata={},
    )

    candidates = await service.discover_candidates(test_db, profile=profile)
    creator_candidates = [c for c in candidates if c.source_strategy == "director"]

    # Verify both movie and show are discovered for the creator
    assert any(c.title == "Fight Club" and c.media_type == "movie" for c in creator_candidates)
    assert any(c.title == "Mindhunter" and c.media_type == "show" for c in creator_candidates)


@pytest.mark.asyncio
async def test_discover_candidates_compound_genres(test_db: Session):
    captured_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        path = request.url.path
        if "/discover/tv" in path:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 1399,
                            "name": "Action TV Show",
                            "first_air_date": "2020-01-01",
                            "genre_ids": [10759],
                            "vote_average": 8.0,
                            "vote_count": 500,
                        }
                    ]
                },
            )
        elif "/discover/movie" in path:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 100,
                            "title": "Action Thriller Movie",
                            "release_date": "2021-01-01",
                            "genre_ids": [28, 53],
                            "vote_average": 7.5,
                            "vote_count": 800,
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"results": []})

    transport = httpx.MockTransport(handler)
    client = TMDBClient(api_key="test_key", transport=transport)
    service = DiscoveryService(tmdb_client=client)

    profile = TasteProfileContent(
        summary="Test",
        genres=[
            WeightedFeature(name="Action/Thriller", weight=0.9, confidence=0.9),
            WeightedFeature(name="History/War", weight=0.8, confidence=0.8),
        ],
        themes=[],
        directors_or_creators=[],
        anti_preferences=[],
        temporary_interests=[],
        metadata={},
    )

    candidates = await service.discover_candidates(test_db, profile=profile)
    # Check that TMDB discover was called with pipe-separated genres
    # Action/Thriller -> Movie 28|53, TV 10759|9648
    assert any("with_genres=28%7C53" in u or "with_genres=28|53" in u for u in captured_urls)
    assert any(
        "with_genres=10759%7C9648" in u or "with_genres=10759|9648" in u for u in captured_urls
    )

    # Check candidates exist
    genre_candidates = [c for c in candidates if c.source_strategy == "profile_genres"]
    assert len(genre_candidates) >= 2
    assert any(c.media_type == "show" for c in genre_candidates)
    assert any(c.media_type == "movie" for c in genre_candidates)
