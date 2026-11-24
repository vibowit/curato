import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import InvalidStateException
from app.integrations.llm.base import LLMProvider
from app.models.base import Base
from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.models.recommendation import Recommendation, RecommendationRun
from app.models.taste import TasteProfile
from app.schemas.recommendation import CandidateItem, RecommendationRunCreateRequest
from app.schemas.taste import TasteProfileContent, WeightedFeature
from app.services.discovery import DiscoveryService
from app.services.recommendations import (
    AntiRecommendationFilter,
    DiversificationService,
    RecommendationService,
    RuleBasedRanker,
)


class MockLLM(LLMProvider):
    def __init__(self, response: Optional[Dict[str, Any]] = None):
        self._response = response or {
            "evaluations": [
                {
                    "candidate_index": 0,
                    "match_score": 92.5,
                    "confidence": 0.88,
                    "positive_factors": ["Świetny klimat neo-noir", "Znakomite aktorstwo"],
                    "risks": [],
                    "reason": "Film idealnie wpisuje się w preferencje mrocznych kryminałów.",
                },
                {
                    "candidate_index": 1,
                    "match_score": 88.0,
                    "confidence": 0.82,
                    "positive_factors": ["Głęboka analiza psychologiczna"],
                    "risks": ["Wolne tempo"],
                    "reason": "Znakomity dramat psychologiczny w reżyserii ulubionego twórcy.",
                },
                {
                    "candidate_index": 2,
                    "match_score": 95.0,
                    "confidence": 0.90,
                    "positive_factors": ["Psychologia kryminalna", "Znakomity reżyser"],
                    "risks": [],
                    "reason": "Wzorcowy serial kryminalny skupiony na profilowaniu.",
                },
            ]
        }

    @property
    def provider_name(self) -> str:
        return "mock_gemini"

    @property
    def model_name(self) -> str:
        return "gemini-2.5-flash-mock"

    async def generate_structured(
        self, prompt: str, system_instruction: Optional[str] = None
    ) -> Dict[str, Any]:
        return self._response


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def sample_profile_content() -> TasteProfileContent:
    return TasteProfileContent(
        summary="Miłośnik kina neo-noir, thrillerów i dramatów psychologicznych.",
        genres=[
            WeightedFeature(name="Crime", weight=0.9, confidence=0.85),
            WeightedFeature(name="Drama", weight=0.85, confidence=0.8),
            WeightedFeature(name="Thriller", weight=0.8, confidence=0.8),
        ],
        themes=[
            WeightedFeature(name="Moral ambiguity and corruption", weight=0.85, confidence=0.8),
        ],
        directors_or_creators=["Denis Villeneuve", "David Fincher"],
        anti_preferences=["Superbohaterowie", "Animacje dla dzieci"],
        temporary_interests=[],
        metadata={"model": "test"},
    )


def test_anti_recommendation_filter_exclusions(test_db: Session):
    # Setup database with watched, plantowatch, rejected, and recent
    # 1. Watched item
    m1 = MediaItem(media_type="movie", title="Sicario", year=2015, tmdb_id=273481)
    test_db.add(m1)
    test_db.flush()
    w1 = WatchHistory(media_item_id=m1.id, status="completed", user_rating=9.0)
    test_db.add(w1)

    # 2. Plan to watch item
    m2 = MediaItem(media_type="movie", title="Dune: Part Two", year=2024, tmdb_id=693134)
    test_db.add(m2)
    test_db.flush()
    w2 = WatchHistory(media_item_id=m2.id, status="plantowatch")
    test_db.add(w2)

    # 3. Rejected recommendation
    m3 = MediaItem(media_type="movie", title="Bad Movie", year=2020, tmdb_id=999999)
    test_db.add(m3)
    test_db.flush()
    run = RecommendationRun(status="completed")
    test_db.add(run)
    test_db.flush()
    rec3 = Recommendation(
        run_id=run.id,
        media_item_id=m3.id,
        match_score=50.0,
        confidence=0.5,
        reason="Test",
        status="rejected",
    )
    test_db.add(rec3)

    # 4. Recently recommended item (status pending, created 2 days ago)
    m4 = MediaItem(media_type="movie", title="Recent Rec", year=2023, tmdb_id=888888)
    test_db.add(m4)
    test_db.flush()
    rec4 = Recommendation(
        run_id=run.id,
        media_item_id=m4.id,
        match_score=85.0,
        confidence=0.8,
        reason="Test",
        status="pending",
        created_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    test_db.add(rec4)
    test_db.commit()

    # Load filter
    anti_filter = AntiRecommendationFilter.load_from_db(test_db, exclude_animation=True)

    # Candidates
    cand_watched = CandidateItem(
        tmdb_id=273481, media_type="movie", title="Sicario", year=2015, source_strategy="test"
    )
    cand_plantowatch = CandidateItem(
        tmdb_id=693134,
        media_type="movie",
        title="Dune: Part Two",
        year=2024,
        source_strategy="test",
    )
    cand_rejected = CandidateItem(
        tmdb_id=999999, media_type="movie", title="Bad Movie", year=2020, source_strategy="test"
    )
    cand_recent = CandidateItem(
        tmdb_id=888888, media_type="movie", title="Recent Rec", year=2023, source_strategy="test"
    )
    cand_animation = CandidateItem(
        tmdb_id=500000,
        media_type="movie",
        title="Anime Film",
        year=2022,
        genre_ids=[16],
        genres=["Animation"],
        source_strategy="test",
    )
    cand_valid = CandidateItem(
        tmdb_id=111111,
        media_type="movie",
        title="Prisoners",
        year=2013,
        genres=["Crime", "Drama"],
        source_strategy="test",
    )

    filtered = anti_filter.filter(
        [
            cand_watched,
            cand_plantowatch,
            cand_rejected,
            cand_recent,
            cand_animation,
            cand_valid,
        ]
    )

    assert len(filtered) == 1
    assert filtered[0].title == "Prisoners"


def test_rule_based_ranker(sample_profile_content: TasteProfileContent):
    c1 = CandidateItem(
        tmdb_id=1,
        media_type="movie",
        title="Generic Comedy",
        vote_average=6.0,
        popularity=10.0,
        genres=["Comedy"],
        overview="A silly comedy about friends.",
        source_strategy="exploration",
    )
    c2 = CandidateItem(
        tmdb_id=2,
        media_type="movie",
        title="Zodiac",
        vote_average=7.9,
        popularity=45.0,
        genres=["Crime", "Drama", "Mystery"],
        director_or_creator="David Fincher",
        overview=(
            "Detectives investigate a series of mysterious killings full of "
            "moral ambiguity and corruption."
        ),
        source_strategy="similar_to_favorites",
    )

    ranker = RuleBasedRanker()
    s1 = ranker.score_candidate(c1, sample_profile_content)
    s2 = ranker.score_candidate(c2, sample_profile_content)

    assert s2 > s1
    top_m, top_s = ranker.select_top_candidates([c1, c2], sample_profile_content, movie_limit=1)
    assert len(top_m) == 1
    assert top_m[0].title == "Zodiac"


def test_diversification_service():
    from app.schemas.recommendation import LLMRecommendationEvaluation

    items = []
    # 3 movies by Denis Villeneuve
    for i in range(3):
        cand = CandidateItem(
            tmdb_id=100 + i,
            media_type="movie",
            title=f"Villeneuve Film {i}",
            director_or_creator="Denis Villeneuve",
            source_strategy="test",
        )
        ev = LLMRecommendationEvaluation(
            candidate_index=i,
            match_score=95.0 - i,
            confidence=0.9,
            reason="Good",
        )
        items.append((cand, ev))

    # 1 movie by David Fincher
    cand_fincher = CandidateItem(
        tmdb_id=200,
        media_type="movie",
        title="Fincher Film",
        director_or_creator="David Fincher",
        source_strategy="test",
    )
    ev_fincher = LLMRecommendationEvaluation(
        candidate_index=3,
        match_score=90.0,
        confidence=0.85,
        reason="Good",
    )
    items.append((cand_fincher, ev_fincher))

    # Diversify with limit 3, max 2 per director
    diversified = DiversificationService.diversify(items, limit=3, max_per_director=2)
    assert len(diversified) == 3

    directors = [cand.director_or_creator for cand, _ in diversified]
    assert directors.count("Denis Villeneuve") == 2
    assert directors.count("David Fincher") == 1


@pytest.mark.asyncio
async def test_recommendation_service_full_run(
    test_db: Session, sample_profile_content: TasteProfileContent
):
    # Add active taste profile
    profile = TasteProfile(
        version="v1.0-gemini",
        active=True,
        profile_json=sample_profile_content.model_dump_json(),
    )
    test_db.add(profile)
    test_db.commit()

    # Mock discovery returning 2 movies and 1 show
    class MockDiscovery(DiscoveryService):
        def __init__(self):
            super().__init__(tmdb_client=None)

        async def discover_candidates(self, db, profile, exclude_genres=None, **kwargs):
            return [
                CandidateItem(
                    tmdb_id=101,
                    media_type="movie",
                    title="Prisoners",
                    year=2013,
                    genres=["Crime", "Drama"],
                    director_or_creator="Denis Villeneuve",
                    vote_average=8.1,
                    overview="A dark thriller about kidnapped children.",
                    source_strategy="similar_to_favorites",
                ),
                CandidateItem(
                    tmdb_id=102,
                    media_type="movie",
                    title="Se7en",
                    year=1995,
                    genres=["Crime", "Mystery"],
                    director_or_creator="David Fincher",
                    vote_average=8.3,
                    overview="Two detectives hunt a serial killer.",
                    source_strategy="director",
                ),
                CandidateItem(
                    tmdb_id=201,
                    media_type="show",
                    title="Mindhunter",
                    year=2017,
                    genres=["Crime", "Drama"],
                    director_or_creator="David Fincher",
                    vote_average=8.6,
                    overview="FBI agents delve into the psychology of murder.",
                    source_strategy="director",
                ),
            ]

    service = RecommendationService(
        discovery_service=MockDiscovery(),
        llm_provider=MockLLM(),
    )

    req = RecommendationRunCreateRequest(movie_limit=2, show_limit=1)
    run = await service.create_recommendation_run(test_db, req)

    assert run.status == "completed"
    assert run.profile_version == "v1.0-gemini"
    assert len(run.recommendations) == 3

    # Check persistence in database
    db_items = test_db.query(MediaItem).all()
    assert len(db_items) == 3
    titles = [item.title for item in db_items]
    assert "Prisoners" in titles
    assert "Mindhunter" in titles

    # Convert to read schema
    schema = service.to_read_schema(run)
    assert schema.status == "completed"
    assert len(schema.recommendations) == 3
    assert schema.recommendations[0].match_score > 0
    assert schema.recommendations[0].reason != ""


@pytest.mark.asyncio
async def test_recommendation_service_no_profile_fails(test_db: Session):
    service = RecommendationService(llm_provider=MockLLM())
    with pytest.raises(InvalidStateException) as exc_info:
        await service.create_recommendation_run(test_db)
    assert exc_info.value.error_code == "INVALID_STATE"


@pytest.mark.asyncio
async def test_recommendation_trailer_hydration_and_get_or_fetch(
    test_db: Session, sample_profile_content
):
    import json
    from unittest.mock import AsyncMock, MagicMock

    profile = TasteProfile(
        version="v1.0-gemini",
        active=True,
        profile_json=sample_profile_content.model_dump_json(),
    )
    test_db.add(profile)
    test_db.commit()

    mock_tmdb = MagicMock()
    mock_tmdb.get_movie_videos = AsyncMock(
        return_value={
            "results": [
                {
                    "site": "YouTube",
                    "key": "test_trailer_key_101",
                    "type": "Trailer",
                    "official": True,
                }
            ]
        }
    )
    mock_tmdb.get_show_videos = AsyncMock(
        return_value={
            "results": [
                {
                    "site": "YouTube",
                    "key": "test_trailer_key_201",
                    "type": "Trailer",
                    "official": True,
                }
            ]
        }
    )
    mock_tmdb.extract_best_trailer.side_effect = lambda res: {
        "trailer_key": res["results"][0]["key"],
        "trailer_url": f"https://www.youtube.com/watch?v={res['results'][0]['key']}",
        "name": "Trailer",
        "site": "YouTube",
    } if res.get("results") else None

    class MockDiscovery(DiscoveryService):
        def __init__(self):
            super().__init__(tmdb_client=mock_tmdb)

        async def discover_candidates(self, db, profile, exclude_genres=None, **kwargs):
            return [
                CandidateItem(
                    tmdb_id=101,
                    media_type="movie",
                    title="Prisoners",
                    year=2013,
                    genres=["Crime", "Drama"],
                    director_or_creator="Denis Villeneuve",
                    vote_average=8.1,
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
                    source_strategy="director",
                ),
            ]

    service = RecommendationService(
        discovery_service=MockDiscovery(),
        llm_provider=MockLLM(),
    )

    req = RecommendationRunCreateRequest(movie_limit=1, show_limit=1)
    run = await service.create_recommendation_run(test_db, req)

    # Verify run succeeded
    assert run.status == "completed"
    schema = service.to_read_schema(run)
    assert len(schema.recommendations) == 2

    rec1 = schema.recommendations[0]
    assert rec1.trailer_key is not None
    assert "https://www.youtube.com/watch?v=" in rec1.trailer_url

    # Check database media_item metadata_json
    media_item = test_db.query(MediaItem).filter(MediaItem.tmdb_id == 101).one()
    meta = json.loads(media_item.metadata_json)
    assert meta["trailer_key"] == "test_trailer_key_101"

    # Test get_or_fetch_trailer
    trailer_res = await service.get_or_fetch_trailer(test_db, rec1.id)
    assert trailer_res.recommendation_id == rec1.id
    assert trailer_res.trailer_key == rec1.trailer_key
    assert trailer_res.trailer_url == rec1.trailer_url


@pytest.mark.asyncio
async def test_create_recommendation_run_with_english_language(test_db: Session):
    taste_profile = TasteProfile(
        version="v1.0-mock",
        profile_json=json.dumps(
            {
                "summary": "Fan of mystery and psychological thrillers.",
                "genres": [{"name": "Mystery", "weight": 0.9, "confidence": 0.85}],
                "themes": [{"name": "Puzzle", "weight": 0.8, "confidence": 0.8}],
                "directors_or_creators": ["David Fincher"],
                "anti_preferences": [],
                "temporary_interests": [],
            }
        ),
        active=True,
    )
    test_db.add(taste_profile)
    test_db.commit()

    class MockDiscovery(DiscoveryService):
        def __init__(self):
            pass

        async def discover_candidates(self, *args, **kwargs):
            return [
                CandidateItem(
                    tmdb_id=201,
                    media_type="movie",
                    title="Se7en",
                    year=1995,
                    genres=["Mystery", "Thriller"],
                    director_or_creator="David Fincher",
                    vote_average=8.3,
                    source_strategy="director",
                ),
            ]

    service = RecommendationService(
        discovery_service=MockDiscovery(),
        llm_provider=MockLLM(),
    )

    req = RecommendationRunCreateRequest(movie_limit=1, show_limit=1, language="en")
    run = await service.create_recommendation_run(test_db, req)
    assert run.status == "completed"
    assert "Successfully generated" in run.summary
    assert "v1.0-mock" in run.summary


def test_rule_based_ranker_wildcard_pool_separation(sample_profile_content: TasteProfileContent):
    ranker = RuleBasedRanker()

    # 3 profile movies
    profile_movies = [
        CandidateItem(
            tmdb_id=i,
            media_type="movie",
            title=f"Profile Movie {i}",
            vote_average=7.5,
            popularity=20.0,
            genres=["Crime", "Drama"],
            source_strategy="profile_genres",
            is_wildcard=False,
        )
        for i in range(1, 4)
    ]
    # 2 wildcard movies
    wildcard_movies = [
        CandidateItem(
            tmdb_id=100 + i,
            media_type="movie",
            title=f"Wildcard Movie {i}",
            vote_average=8.2,
            popularity=15.0,
            genres=["Western"],
            source_strategy="exploration",
            is_wildcard=True,
        )
        for i in range(1, 3)
    ]

    selected_movies, selected_shows = ranker.select_top_candidates(
        candidates=profile_movies + wildcard_movies,
        profile=sample_profile_content,
        movie_limit=2,
        wildcard_movie_limit=1,
    )
    # 2 profile + 1 wildcard = 3 movies
    assert len(selected_movies) == 3
    wildcards = [m for m in selected_movies if m.is_wildcard]
    profiles = [m for m in selected_movies if not m.is_wildcard]
    assert len(wildcards) == 1
    assert len(profiles) == 2


def test_diversification_guarantees_wildcard_slot():
    from app.schemas.recommendation import LLMRecommendationEvaluation

    items = []
    # 10 profile movies
    for i in range(10):
        cand = CandidateItem(
            tmdb_id=i,
            media_type="movie",
            title=f"Movie {i}",
            vote_average=7.5,
            source_strategy="profile_genres",
            is_wildcard=False,
        )
        ev = LLMRecommendationEvaluation(
            candidate_index=i,
            match_score=95.0 - i,
            confidence=0.9,
            reason="Good fit",
        )
        items.append((cand, ev))

    # 2 wildcard movies
    for i in range(2):
        cand = CandidateItem(
            tmdb_id=100 + i,
            media_type="movie",
            title=f"Wildcard {i}",
            vote_average=8.5,
            source_strategy="exploration",
            is_wildcard=True,
        )
        ev = LLMRecommendationEvaluation(
            candidate_index=10 + i,
            match_score=80.0 - i,  # lower score than profile items
            confidence=0.85,
            reason="Horizon broadener",
        )
        items.append((cand, ev))

    # Diversify for 10 movies with include_wildcards=True
    diversified = DiversificationService.diversify(
        items, limit=10, max_per_director=2, include_wildcards=True
    )
    assert len(diversified) == 10
    wildcards = [c for c, _ in diversified if c.is_wildcard]
    profiles = [c for c, _ in diversified if not c.is_wildcard]
    assert len(wildcards) == 1
    assert len(profiles) == 9
    assert wildcards[0].title == "Wildcard 0"


@pytest.mark.asyncio
async def test_create_recommendation_run_persists_is_wildcard(test_db: Session):
    taste_profile = TasteProfile(
        version="v2.0-wildcard-test",
        profile_json=json.dumps(
            {
                "summary": "Lover of crime and thrillers.",
                "genres": [{"name": "Crime", "weight": 0.9, "confidence": 0.9}],
                "themes": [],
                "directors_or_creators": [],
                "anti_preferences": [],
                "temporary_interests": [],
            }
        ),
        active=True,
    )
    test_db.add(taste_profile)
    test_db.commit()

    class MockDiscoveryWithWildcard(DiscoveryService):
        def __init__(self):
            pass

        async def discover_candidates(self, *args, **kwargs):
            return [
                CandidateItem(
                    tmdb_id=10,
                    media_type="movie",
                    title="Profile Movie 1",
                    genres=["Crime"],
                    vote_average=8.0,
                    source_strategy="profile_genres",
                    is_wildcard=False,
                ),
                CandidateItem(
                    tmdb_id=20,
                    media_type="movie",
                    title="Wildcard Movie",
                    genres=["Comedy"],
                    vote_average=8.5,
                    source_strategy="exploration",
                    is_wildcard=True,
                ),
                CandidateItem(
                    tmdb_id=30,
                    media_type="show",
                    title="Profile Show 1",
                    genres=["Crime"],
                    vote_average=8.2,
                    source_strategy="profile_genres",
                    is_wildcard=False,
                ),
                CandidateItem(
                    tmdb_id=40,
                    media_type="show",
                    title="Wildcard Show",
                    genres=["Documentary"],
                    vote_average=8.6,
                    source_strategy="exploration",
                    is_wildcard=True,
                ),
            ]

    service = RecommendationService(
        discovery_service=MockDiscoveryWithWildcard(),
        llm_provider=MockLLM(),
    )

    req = RecommendationRunCreateRequest(movie_limit=2, show_limit=2, include_wildcards=True)
    run = await service.create_recommendation_run(test_db, req)
    assert run.status == "completed"

    schema = service.to_read_schema(run)
    assert len(schema.recommendations) == 4

    movies = [r for r in schema.recommendations if r.media_item.media_type == "movie"]
    shows = [r for r in schema.recommendations if r.media_item.media_type == "show"]

    assert len([m for m in movies if m.is_wildcard]) == 1
    assert len([m for m in movies if not m.is_wildcard]) == 1
    assert len([s for s in shows if s.is_wildcard]) == 1
    assert len([s for s in shows if not s.is_wildcard]) == 1

