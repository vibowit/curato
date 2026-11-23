import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.integrations.tmdb import (
    TMDB_GENRE_NAMES,
    TMDB_MOVIE_GENRES,
    TMDB_TV_GENRES,
    TMDBAuthError,
    TMDBClient,
    resolve_tmdb_genre_ids,
)
from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.schemas.recommendation import CandidateItem
from app.schemas.taste import TasteProfileContent
from app.services.locale import locale_service

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Discovers and normalizes movie and TV show candidates from TMDB

    based on the user's taste profile, favorite items, and directors.
    """

    def __init__(self, tmdb_client: Optional[TMDBClient] = None):
        self.tmdb = tmdb_client or TMDBClient()

    @staticmethod
    def _extract_year(date_str: Optional[str]) -> Optional[int]:
        if not date_str or len(date_str) < 4:
            return None
        try:
            return int(date_str[:4])
        except ValueError:
            return None

    @staticmethod
    def _map_genre_ids(genre_ids: List[int]) -> List[str]:
        return [TMDB_GENRE_NAMES[gid] for gid in genre_ids if gid in TMDB_GENRE_NAMES]

    def _normalize_movie(
        self, raw: Dict[str, Any], strategy: str, director: Optional[str] = None
    ) -> Optional[CandidateItem]:
        tmdb_id = raw.get("id")
        title = raw.get("title")
        if not tmdb_id or not title:
            return None

        genre_ids = raw.get("genre_ids") or []
        genres = self._map_genre_ids(genre_ids)
        year = self._extract_year(raw.get("release_date"))

        return CandidateItem(
            tmdb_id=tmdb_id,
            media_type="movie",
            title=title,
            year=year,
            overview=raw.get("overview") or "",
            genres=genres,
            genre_ids=genre_ids,
            director_or_creator=director,
            vote_average=float(raw.get("vote_average", 0.0)),
            vote_count=int(raw.get("vote_count", 0)),
            popularity=float(raw.get("popularity", 0.0)),
            poster_path=raw.get("poster_path"),
            source_strategy=strategy,
        )

    def _normalize_show(
        self, raw: Dict[str, Any], strategy: str, creator: Optional[str] = None
    ) -> Optional[CandidateItem]:
        tmdb_id = raw.get("id")
        title = raw.get("name")
        if not tmdb_id or not title:
            return None

        genre_ids = raw.get("genre_ids") or []
        genres = self._map_genre_ids(genre_ids)
        year = self._extract_year(raw.get("first_air_date"))

        return CandidateItem(
            tmdb_id=tmdb_id,
            media_type="show",
            title=title,
            year=year,
            overview=raw.get("overview") or "",
            genres=genres,
            genre_ids=genre_ids,
            director_or_creator=creator,
            vote_average=float(raw.get("vote_average", 0.0)),
            vote_count=int(raw.get("vote_count", 0)),
            popularity=float(raw.get("popularity", 0.0)),
            poster_path=raw.get("poster_path"),
            source_strategy=strategy,
        )

    async def get_favorites_from_db(
        self,
        db: Session,
        limit: int = 15,
        movie_limit: Optional[int] = None,
        show_limit: Optional[int] = None,
    ) -> List[MediaItem]:
        """Fetches user's top-rated or completed items with TMDB IDs from local database,

        balancing movies and TV shows so neither starves the discovery pool.
        """
        if movie_limit is None and show_limit is None:
            movie_limit = max(1, limit // 2)
            show_limit = max(1, limit - movie_limit)
        elif movie_limit is None:
            movie_limit = max(0, limit - (show_limit or 0))
        elif show_limit is None:
            show_limit = max(0, limit - (movie_limit or 0))

        def query_type(m_type: str, sub_limit: int) -> List[MediaItem]:
            if sub_limit <= 0:
                return []
            stmt = (
                select(MediaItem)
                .join(WatchHistory, MediaItem.id == WatchHistory.media_item_id)
                .where(
                    MediaItem.tmdb_id.is_not(None),
                    MediaItem.media_type == m_type,
                    (WatchHistory.user_rating >= 7.5) | (WatchHistory.status == "completed"),
                )
                .order_by(desc(WatchHistory.user_rating), desc(WatchHistory.watched_at))
                .limit(sub_limit)
            )
            return list(db.execute(stmt).scalars().all())

        fav_movies = query_type("movie", movie_limit)
        fav_shows = query_type("show", show_limit)

        # Backfill if one type has fewer items than allocated
        if len(fav_movies) < movie_limit and show_limit > 0:
            extra = movie_limit - len(fav_movies)
            additional_shows = query_type("show", show_limit + extra)
            fav_shows = additional_shows
        elif len(fav_shows) < show_limit and movie_limit > 0:
            extra = show_limit - len(fav_shows)
            additional_movies = query_type("movie", movie_limit + extra)
            fav_movies = additional_movies

        return fav_movies + fav_shows

    async def discover_candidates(
        self,
        db: Session,
        profile: TasteProfileContent,
        exclude_genres: Optional[List[str]] = None,
        target_movies_pool: int = 60,
        target_shows_pool: int = 35,
        language: Optional[str] = None,
    ) -> List[CandidateItem]:
        """Harvests candidates across 4 distinct strategies concurrently."""
        candidates_map: Dict[tuple[str, int], CandidateItem] = {}
        sem = asyncio.Semaphore(5)

        if language:
            self.tmdb.default_language = locale_service.get_tmdb_language(language)

        # 1. Determine without_genres (e.g. animation)
        without_genres_set: Set[str] = set()
        if exclude_genres:
            without_genres_set.update(g.lower() for g in exclude_genres)
        for anti in profile.anti_preferences:
            if "anim" in anti.lower():
                without_genres_set.add("animation")

        movie_without_ids = ",".join(
            str(TMDB_MOVIE_GENRES[g]) for g in without_genres_set if g in TMDB_MOVIE_GENRES
        )
        show_without_ids = ",".join(
            str(TMDB_TV_GENRES[g]) for g in without_genres_set if g in TMDB_TV_GENRES
        )

        tasks = []

        # 2. Strategy A: Similar to favorites (40%)
        fav_items = await self.get_favorites_from_db(db, limit=10)

        async def fetch_fav_recommendations(fav: MediaItem) -> List[Optional[CandidateItem]]:
            if not fav.tmdb_id:
                return []
            async with sem:
                try:
                    if fav.media_type == "movie":
                        res = await self.tmdb.get_movie_recommendations(fav.tmdb_id)
                        return [
                            self._normalize_movie(item, strategy="similar_to_favorites")
                            for item in res.get("results", [])[:8]
                        ]
                    elif fav.media_type == "show":
                        res = await self.tmdb.get_show_recommendations(fav.tmdb_id)
                        return [
                            self._normalize_show(item, strategy="similar_to_favorites")
                            for item in res.get("results", [])[:6]
                        ]
                except TMDBAuthError:
                    raise
                except Exception as e:
                    logger.debug(
                        "Failed getting recommendations for %s (%d): %s", fav.title, fav.tmdb_id, e
                    )
            return []

        for fav in fav_items:
            tasks.append(fetch_fav_recommendations(fav))

        # 3. Strategy B: Preferred genres from profile (35%)
        sorted_genres = sorted(profile.genres, key=lambda g: g.weight * g.confidence, reverse=True)
        top_genres = sorted_genres[:3]

        async def fetch_genre_movies(g_name: str, g_id: str) -> List[Optional[CandidateItem]]:
            async with sem:
                try:
                    res_m = await self.tmdb.discover_movies(
                        with_genres=g_id,
                        without_genres=movie_without_ids or None,
                        vote_count_gte=100,
                        vote_average_gte=7.0,
                    )
                    return [
                        self._normalize_movie(item, strategy="profile_genres")
                        for item in res_m.get("results", [])[:10]
                    ]
                except TMDBAuthError:
                    raise
                except Exception as e:
                    logger.debug("Error discovering movies for genre %s: %s", g_name, e)
            return []

        async def fetch_genre_shows(g_name: str, g_id: str) -> List[Optional[CandidateItem]]:
            async with sem:
                try:
                    res_s = await self.tmdb.discover_shows(
                        with_genres=g_id,
                        without_genres=show_without_ids or None,
                        vote_count_gte=50,
                        vote_average_gte=7.0,
                    )
                    return [
                        self._normalize_show(item, strategy="profile_genres")
                        for item in res_s.get("results", [])[:8]
                    ]
                except TMDBAuthError:
                    raise
                except Exception as e:
                    logger.debug("Error discovering shows for genre %s: %s", g_name, e)
            return []

        for genre in top_genres:
            movie_genre_ids = resolve_tmdb_genre_ids(genre.name, media_type="movie")
            if movie_genre_ids:
                tasks.append(
                    fetch_genre_movies(genre.name, "|".join(str(gid) for gid in movie_genre_ids))
                )
            show_genre_ids = resolve_tmdb_genre_ids(genre.name, media_type="show")
            if show_genre_ids:
                tasks.append(
                    fetch_genre_shows(genre.name, "|".join(str(gid) for gid in show_genre_ids))
                )

        # 4. Strategy C: Favorite directors and creators (15%)
        async def fetch_creator_candidates(creator: str) -> List[Optional[CandidateItem]]:
            async with sem:
                try:
                    person_res = await self.tmdb.search_person(creator)
                    persons = person_res.get("results", [])
                    if not persons:
                        return []
                    person_id = persons[0]["id"]

                    creator_items: List[Optional[CandidateItem]] = []

                    # 4a. Movies directed/created by creator
                    crew_res = await self.tmdb.discover_movies(
                        with_crew=str(person_id),
                        without_genres=movie_without_ids or None,
                        vote_count_gte=30,
                    )
                    creator_items.extend(
                        self._normalize_movie(item, strategy="director", director=creator)
                        for item in crew_res.get("results", [])[:5]
                    )

                    # 4b. TV shows created/written/directed/executive-produced by creator
                    tv_credits = await self.tmdb.get_person_tv_credits(person_id)
                    crew = tv_credits.get("crew", [])
                    relevant_jobs = {
                        "creator",
                        "director",
                        "writer",
                        "executive producer",
                        "showrunner",
                    }
                    relevant_depts = {"directing", "writing", "production", "creator"}

                    shows_by_id: Dict[int, Dict[str, Any]] = {}
                    for item in crew:
                        job = str(item.get("job", "")).lower()
                        dept = str(item.get("department", "")).lower()
                        if job in relevant_jobs or dept in relevant_depts:
                            s_id = item.get("id")
                            if s_id and s_id not in shows_by_id:
                                if item.get("vote_count", 0) >= 20:
                                    g_ids = item.get("genre_ids", [])
                                    if without_genres_set and any(
                                        TMDB_GENRE_NAMES.get(gid, "").lower() in without_genres_set
                                        for gid in g_ids
                                    ):
                                        continue
                                    shows_by_id[s_id] = item

                    sorted_shows = sorted(
                        shows_by_id.values(),
                        key=lambda x: (
                            float(x.get("vote_average", 0.0)),
                            float(x.get("popularity", 0.0)),
                        ),
                        reverse=True,
                    )
                    creator_items.extend(
                        self._normalize_show(item, strategy="director", creator=creator)
                        for item in sorted_shows[:5]
                    )
                    return creator_items
                except TMDBAuthError:
                    raise
                except Exception as e:
                    logger.debug("Error searching creator %s: %s", creator, e)
            return []

        for creator in profile.directors_or_creators[:4]:
            tasks.append(fetch_creator_candidates(creator))

        # 5. Strategy D: Exploration (10%) - high quality items
        async def fetch_exploration_movies() -> List[Optional[CandidateItem]]:
            async with sem:
                try:
                    exp_m = await self.tmdb.discover_movies(
                        without_genres=movie_without_ids or None,
                        sort_by="vote_average.desc",
                        vote_count_gte=300,
                        vote_average_gte=7.8,
                    )
                    return [
                        self._normalize_movie(item, strategy="exploration")
                        for item in exp_m.get("results", [])[:8]
                    ]
                except TMDBAuthError:
                    raise
                except Exception as e:
                    logger.debug("Error during exploration movies discovery: %s", e)
            return []

        async def fetch_exploration_shows() -> List[Optional[CandidateItem]]:
            async with sem:
                try:
                    exp_s = await self.tmdb.discover_shows(
                        without_genres=show_without_ids or None,
                        sort_by="vote_average.desc",
                        vote_count_gte=150,
                        vote_average_gte=8.0,
                    )
                    return [
                        self._normalize_show(item, strategy="exploration")
                        for item in exp_s.get("results", [])[:6]
                    ]
                except TMDBAuthError:
                    raise
                except Exception as e:
                    logger.debug("Error during exploration shows discovery: %s", e)
            return []

        tasks.append(fetch_exploration_movies())
        tasks.append(fetch_exploration_shows())

        # Execute all discovery tasks concurrently
        results = await asyncio.gather(*tasks)
        for batch in results:
            for cand in batch:
                if cand and (cand.media_type, cand.tmdb_id) not in candidates_map:
                    candidates_map[(cand.media_type, cand.tmdb_id)] = cand

        return list(candidates_map.values())
