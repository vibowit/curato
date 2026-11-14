import logging
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.integrations.tmdb import (
    TMDB_GENRE_NAMES,
    TMDB_MOVIE_GENRES,
    TMDB_TV_GENRES,
    TMDBClient,
)
from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.schemas.recommendation import CandidateItem
from app.schemas.taste import TasteProfileContent

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
        self, db: Session, limit: int = 15
    ) -> List[MediaItem]:
        """Fetches user's top-rated or completed items with TMDB IDs from local database."""
        stmt = (
            select(MediaItem)
            .join(WatchHistory, MediaItem.id == WatchHistory.media_item_id)
            .where(
                MediaItem.tmdb_id.is_not(None),
                (WatchHistory.user_rating >= 7.5) | (WatchHistory.status == "completed"),
            )
            .order_by(desc(WatchHistory.user_rating), desc(WatchHistory.watched_at))
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    async def discover_candidates(
        self,
        db: Session,
        profile: TasteProfileContent,
        exclude_genres: Optional[List[str]] = None,
        target_movies_pool: int = 60,
        target_shows_pool: int = 35,
    ) -> List[CandidateItem]:
        """Harvests candidates across 4 distinct strategies to build a balanced pool."""
        candidates_map: Dict[tuple[str, int], CandidateItem] = {}

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

        # 2. Strategy A: Similar to favorites (40%)
        fav_items = await self.get_favorites_from_db(db, limit=10)
        for fav in fav_items:
            if not fav.tmdb_id:
                continue
            try:
                if fav.media_type == "movie":
                    res = await self.tmdb.get_movie_recommendations(fav.tmdb_id)
                    for item in res.get("results", [])[:8]:
                        cand = self._normalize_movie(item, strategy="similar_to_favorites")
                        if cand and (cand.media_type, cand.tmdb_id) not in candidates_map:
                            candidates_map[(cand.media_type, cand.tmdb_id)] = cand
                elif fav.media_type == "show":
                    res = await self.tmdb.get_show_recommendations(fav.tmdb_id)
                    for item in res.get("results", [])[:6]:
                        cand = self._normalize_show(item, strategy="similar_to_favorites")
                        if cand and (cand.media_type, cand.tmdb_id) not in candidates_map:
                            candidates_map[(cand.media_type, cand.tmdb_id)] = cand
            except Exception as e:
                logger.debug(
                    "Failed getting recommendations for %s (%d): %s", fav.title, fav.tmdb_id, e
                )

        # 3. Strategy B: Preferred genres from profile (35%)
        # Take top 3 genres sorted by weight
        sorted_genres = sorted(profile.genres, key=lambda g: g.weight * g.confidence, reverse=True)
        top_genres = sorted_genres[:3]

        for genre in top_genres:
            g_name = genre.name.lower()
            if g_name in TMDB_MOVIE_GENRES:
                g_id = str(TMDB_MOVIE_GENRES[g_name])
                try:
                    res_m = await self.tmdb.discover_movies(
                        with_genres=g_id,
                        without_genres=movie_without_ids or None,
                        vote_count_gte=100,
                        vote_average_gte=7.0,
                    )
                    for item in res_m.get("results", [])[:10]:
                        cand = self._normalize_movie(item, strategy="profile_genres")
                        if cand and (cand.media_type, cand.tmdb_id) not in candidates_map:
                            candidates_map[(cand.media_type, cand.tmdb_id)] = cand
                except Exception as e:
                    logger.debug("Error discovering movies for genre %s: %s", g_name, e)

            if g_name in TMDB_TV_GENRES:
                g_id = str(TMDB_TV_GENRES[g_name])
                try:
                    res_s = await self.tmdb.discover_shows(
                        with_genres=g_id,
                        without_genres=show_without_ids or None,
                        vote_count_gte=50,
                        vote_average_gte=7.0,
                    )
                    for item in res_s.get("results", [])[:8]:
                        cand = self._normalize_show(item, strategy="profile_genres")
                        if cand and (cand.media_type, cand.tmdb_id) not in candidates_map:
                            candidates_map[(cand.media_type, cand.tmdb_id)] = cand
                except Exception as e:
                    logger.debug("Error discovering shows for genre %s: %s", g_name, e)

        # 4. Strategy C: Favorite directors and creators (15%)
        for creator in profile.directors_or_creators[:4]:
            try:
                person_res = await self.tmdb.search_person(creator)
                persons = person_res.get("results", [])
                if persons:
                    person_id = persons[0]["id"]
                    crew_res = await self.tmdb.discover_movies(
                        with_crew=str(person_id),
                        without_genres=movie_without_ids or None,
                        vote_count_gte=30,
                    )
                    for item in crew_res.get("results", [])[:5]:
                        cand = self._normalize_movie(item, strategy="director", director=creator)
                        if cand and (cand.media_type, cand.tmdb_id) not in candidates_map:
                            candidates_map[(cand.media_type, cand.tmdb_id)] = cand
            except Exception as e:
                logger.debug("Error searching creator %s: %s", creator, e)

        # 5. Strategy D: Exploration (10%) - high quality items
        try:
            exp_m = await self.tmdb.discover_movies(
                without_genres=movie_without_ids or None,
                sort_by="vote_average.desc",
                vote_count_gte=300,
                vote_average_gte=7.8,
            )
            for item in exp_m.get("results", [])[:8]:
                cand = self._normalize_movie(item, strategy="exploration")
                if cand and (cand.media_type, cand.tmdb_id) not in candidates_map:
                    candidates_map[(cand.media_type, cand.tmdb_id)] = cand

            exp_s = await self.tmdb.discover_shows(
                without_genres=show_without_ids or None,
                sort_by="vote_average.desc",
                vote_count_gte=150,
                vote_average_gte=8.0,
            )
            for item in exp_s.get("results", [])[:6]:
                cand = self._normalize_show(item, strategy="exploration")
                if cand and (cand.media_type, cand.tmdb_id) not in candidates_map:
                    candidates_map[(cand.media_type, cand.tmdb_id)] = cand
        except Exception as e:
            logger.debug("Error during exploration discovery: %s", e)

        return list(candidates_map.values())
