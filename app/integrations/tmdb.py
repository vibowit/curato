import asyncio
import logging
import time
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Standard TMDB genre mappings for reference and query construction
TMDB_MOVIE_GENRES: Dict[str, int] = {
    "action": 28,
    "adventure": 12,
    "animation": 16,
    "comedy": 35,
    "crime": 80,
    "documentary": 99,
    "drama": 18,
    "family": 10751,
    "fantasy": 14,
    "history": 36,
    "horror": 27,
    "music": 10402,
    "mystery": 9648,
    "romance": 10749,
    "science fiction": 878,
    "sci-fi": 878,
    "thriller": 53,
    "war": 10752,
    "western": 37,
}

TMDB_TV_GENRES: Dict[str, int] = {
    "action & adventure": 10759,
    "action": 10759,
    "animation": 16,
    "comedy": 35,
    "crime": 80,
    "documentary": 99,
    "drama": 18,
    "mystery": 9648,
    "sci-fi & fantasy": 10765,
    "sci-fi": 10765,
    "war & politics": 10768,
    "western": 37,
}

TMDB_GENRE_NAMES: Dict[int, str] = {
    28: "Action",
    12: "Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    14: "Fantasy",
    36: "History",
    27: "Horror",
    10402: "Music",
    9648: "Mystery",
    10749: "Romance",
    878: "Science Fiction",
    10770: "TV Movie",
    53: "Thriller",
    10752: "War",
    37: "Western",
    10759: "Action & Adventure",
    10762: "Kids",
    10763: "News",
    10764: "Reality",
    10765: "Sci-Fi & Fantasy",
    10766: "Soap",
    10767: "Talk",
    10768: "War & Politics",
}


class TMDBError(Exception):
    """Base exception for TMDB API errors."""

    def __init__(
        self, message: str, code: str = "UPSTREAM_ERROR", status_code: Optional[int] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class TMDBAuthError(TMDBError):
    """Raised when TMDB authentication fails (401)."""

    def __init__(self, message: str = "TMDB authentication failed"):
        super().__init__(message, code="AUTH_REQUIRED", status_code=401)


class TMDBRateLimitError(TMDBError):
    """Raised when TMDB rate limit is exceeded (429)."""

    def __init__(self, message: str = "TMDB rate limit exceeded"):
        super().__init__(message, code="RATE_LIMITED", status_code=429)


class TMDBUpstreamError(TMDBError):
    """Raised when TMDB returns upstream error or is unreachable."""

    def __init__(self, message: str = "TMDB upstream error", status_code: Optional[int] = 502):
        super().__init__(message, code="UPSTREAM_ERROR", status_code=status_code)


class TMDBClient:
    """Asynchronous HTTP client for The Movie Database (TMDB) API v3/v4."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        read_access_token: Optional[str] = None,
        base_url: str = "https://api.themoviedb.org/3",
        timeout: float = 15.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        max_retries: int = 3,
        rate_limit_per_second: float = 20.0,
        default_language: Optional[str] = None,
    ):
        raw_key = api_key or (
            settings.TMDB_API_KEY.get_secret_value() if settings.TMDB_API_KEY else None
        )
        raw_token = read_access_token or (
            settings.TMDB_READ_ACCESS_TOKEN.get_secret_value()
            if settings.TMDB_READ_ACCESS_TOKEN
            else None
        )

        # Detect if user pasted v4 JWT Bearer token into TMDB_API_KEY
        if raw_key and raw_key.startswith("eyJ") and not raw_token:
            raw_token = raw_key
            raw_key = None

        # Ignore placeholder values from .env.example
        if raw_key and ("your_" in raw_key or "here" in raw_key):
            raw_key = None
        if raw_token and ("your_" in raw_token or "here" in raw_token):
            raw_token = None

        self.api_key = raw_key
        self.read_access_token = raw_token
        self.default_language = default_language
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_request_interval = 1.0 / rate_limit_per_second
        self._last_request_time: float = 0.0

        headers = {
            "Accept": "application/json",
            "User-Agent": "MovieRecommender/1.0",
        }
        if self.read_access_token:
            headers["Authorization"] = f"Bearer {self.read_access_token}"

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        """Closes the underlying HTTP client session."""
        await self._client.aclose()

    async def __aenter__(self) -> "TMDBClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()

    async def _throttle(self) -> None:
        """Simple throttling mechanism to prevent exceeding TMDB rate limits."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.min_request_interval:
            await asyncio.sleep(self.min_request_interval - elapsed)
        self._last_request_time = time.monotonic()

    def _prepare_params(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Injects api_key if Bearer token is not present and language if configured."""
        query_params = dict(params or {})
        if not self.read_access_token and self.api_key:
            query_params["api_key"] = self.api_key
        if self.default_language and "language" not in query_params:
            query_params["language"] = self.default_language
        return query_params

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Performs HTTP request with rate limiting and exponential backoff retry."""
        if not self.read_access_token and not self.api_key:
            raise TMDBAuthError(
                "Brak poprawnego klucza TMDB_API_KEY w pliku .env "
                "(brak wartości lub domyślny placeholder 'your_tmdb_api_key_here')."
            )

        url = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        query_params = self._prepare_params(params)

        for attempt in range(1, self.max_retries + 1):
            await self._throttle()
            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    params=query_params,
                )

                if response.status_code == 401:
                    logger.error("TMDB API 401 Unauthorized for endpoint: %s", url)
                    raise TMDBAuthError("Invalid TMDB credentials or missing API key.")

                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", 1.5))
                    logger.warning(
                        "TMDB 429 Rate limited. Attempt %d/%d. Waiting %.2fs...",
                        attempt,
                        self.max_retries,
                        retry_after,
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(retry_after)
                        continue
                    raise TMDBRateLimitError("TMDB rate limit exceeded.")

                if response.status_code >= 500:
                    logger.warning(
                        "TMDB upstream server error HTTP %d. Attempt %d/%d.",
                        response.status_code,
                        attempt,
                        self.max_retries,
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                        continue
                    raise TMDBUpstreamError(
                        f"TMDB upstream server error {response.status_code}.",
                        status_code=response.status_code,
                    )

                response.raise_for_status()
                return response.json()

            except (httpx.ConnectError, httpx.TimeoutException) as net_err:
                logger.warning(
                    "Network error connecting to TMDB (%s). Attempt %d/%d.",
                    net_err,
                    attempt,
                    self.max_retries,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
                raise TMDBUpstreamError(
                    f"Failed to communicate with TMDB API: {net_err}"
                ) from net_err

        raise TMDBUpstreamError("Maximum retries exhausted connecting to TMDB.")

    async def discover_movies(
        self,
        with_genres: Optional[str] = None,
        without_genres: Optional[str] = None,
        with_crew: Optional[str] = None,
        sort_by: str = "popularity.desc",
        vote_count_gte: int = 50,
        vote_average_gte: Optional[float] = None,
        page: int = 1,
    ) -> Dict[str, Any]:
        """Discovers movies matching criteria."""
        params: Dict[str, Any] = {
            "sort_by": sort_by,
            "vote_count.gte": vote_count_gte,
            "page": page,
            "include_adult": "false",
        }
        if with_genres:
            params["with_genres"] = with_genres
        if without_genres:
            params["without_genres"] = without_genres
        if with_crew:
            params["with_crew"] = with_crew
        if vote_average_gte is not None:
            params["vote_average.gte"] = vote_average_gte

        return await self._request("GET", "/discover/movie", params=params)

    async def discover_shows(
        self,
        with_genres: Optional[str] = None,
        without_genres: Optional[str] = None,
        sort_by: str = "popularity.desc",
        vote_count_gte: int = 30,
        vote_average_gte: Optional[float] = None,
        page: int = 1,
    ) -> Dict[str, Any]:
        """Discovers TV shows matching criteria."""
        params: Dict[str, Any] = {
            "sort_by": sort_by,
            "vote_count.gte": vote_count_gte,
            "page": page,
            "include_adult": "false",
        }
        if with_genres:
            params["with_genres"] = with_genres
        if without_genres:
            params["without_genres"] = without_genres
        if vote_average_gte is not None:
            params["vote_average.gte"] = vote_average_gte

        return await self._request("GET", "/discover/tv", params=params)

    async def get_movie_recommendations(self, movie_id: int, page: int = 1) -> Dict[str, Any]:
        """Gets recommended movies for a given movie ID (with fallback to similar)."""
        try:
            res = await self._request(
                "GET", f"/movie/{movie_id}/recommendations", params={"page": page}
            )
            if res.get("results"):
                return res
        except TMDBError:
            pass
        return await self._request("GET", f"/movie/{movie_id}/similar", params={"page": page})

    async def get_show_recommendations(self, show_id: int, page: int = 1) -> Dict[str, Any]:
        """Gets recommended TV shows for a given show ID (with fallback to similar)."""
        try:
            res = await self._request(
                "GET", f"/tv/{show_id}/recommendations", params={"page": page}
            )
            if res.get("results"):
                return res
        except TMDBError:
            pass
        return await self._request("GET", f"/tv/{show_id}/similar", params={"page": page})

    async def search_person(self, query: str) -> Dict[str, Any]:
        """Searches for a person (actor/director) by name."""
        return await self._request("GET", "/search/person", params={"query": query})

    async def get_person_movie_credits(self, person_id: int) -> Dict[str, Any]:
        """Gets movie credits for a person."""
        return await self._request("GET", f"/person/{person_id}/movie_credits")

    async def get_movie_details(
        self, movie_id: int, append_to_response: str = "external_ids,credits"
    ) -> Dict[str, Any]:
        """Gets full movie details including external IDs (IMDB) and cast/crew."""
        return await self._request(
            "GET", f"/movie/{movie_id}", params={"append_to_response": append_to_response}
        )

    async def get_show_details(
        self, show_id: int, append_to_response: str = "external_ids,credits"
    ) -> Dict[str, Any]:
        """Gets full TV show details including external IDs and creators."""
        return await self._request(
            "GET", f"/tv/{show_id}", params={"append_to_response": append_to_response}
        )

    async def get_movie_videos(self, movie_id: int) -> Dict[str, Any]:
        """Gets video clips and trailers for a movie."""
        return await self._request("GET", f"/movie/{movie_id}/videos")

    async def get_show_videos(self, show_id: int) -> Dict[str, Any]:
        """Gets video clips and trailers for a TV show."""
        return await self._request("GET", f"/tv/{show_id}/videos")

    @staticmethod
    def extract_best_trailer(videos_payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Extracts the best matching YouTube trailer from TMDB videos payload.

        Prioritizes:
        1. Official YouTube Trailer
        2. YouTube Trailer (non-official)
        3. YouTube Teaser
        4. Any YouTube Video
        """
        results = videos_payload.get("results") or []
        yt_videos = [v for v in results if v.get("site") == "YouTube" and v.get("key")]
        if not yt_videos:
            return None

        def trailer_score(v: Dict[str, Any]) -> int:
            v_type = str(v.get("type", "")).lower()
            official = bool(v.get("official", False))
            score = 0
            if v_type == "trailer":
                score += 100
                if official:
                    score += 50
            elif v_type == "teaser":
                score += 50
                if official:
                    score += 20
            elif v_type == "clip":
                score += 10
            return score

        best_video = max(yt_videos, key=trailer_score)
        key = best_video["key"]
        return {
            "trailer_key": key,
            "trailer_url": f"https://www.youtube.com/watch?v={key}",
            "name": best_video.get("name", "Trailer"),
            "site": "YouTube",
        }
