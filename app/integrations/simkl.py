import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class SimklError(Exception):
    """Base exception for all Simkl integration errors."""

    def __init__(
        self,
        message: str,
        code: str = "UPSTREAM_ERROR",
        status_code: Optional[int] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class SimklAuthError(SimklError):
    """Raised when authentication fails (401, 403)."""

    def __init__(self, message: str = "Simkl authentication failed"):
        super().__init__(message, code="AUTH_REQUIRED", status_code=401)


class SimklRateLimitError(SimklError):
    """Raised when Simkl rate limits are exceeded (429)."""

    def __init__(self, message: str = "Simkl rate limit exceeded"):
        super().__init__(message, code="RATE_LIMITED", status_code=429)


class SimklUpstreamError(SimklError):
    """Raised when Simkl API returns server errors or is unreachable."""

    def __init__(self, message: str = "Simkl API upstream error", status_code: Optional[int] = 502):
        super().__init__(message, code="UPSTREAM_ERROR", status_code=status_code)


class SimklClient:
    """Asynchronous HTTP client for the Simkl API (v2)."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        user_token: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        max_retries: int = 3,
    ):
        self.client_id = client_id or (
            settings.SIMKL_CLIENT_ID.get_secret_value() if settings.SIMKL_CLIENT_ID else None
        )
        self.user_token = user_token or (
            settings.effective_simkl_token.get_secret_value()
            if settings.effective_simkl_token
            else None
        )
        self.base_url = (base_url or settings.SIMKL_BASE_URL).rstrip("/")
        self.timeout = timeout or settings.SIMKL_TIMEOUT_SECONDS
        self.transport = transport
        self.max_retries = max_retries

        # Rate limiting state
        self._last_get_time: float = 0.0
        self._last_post_time: float = 0.0
        self._min_get_interval: float = 0.1  # 10 GET/sec max
        self._min_post_interval: float = 1.0  # 1 POST/sec max

        # Safety invariant tracker
        self.write_calls_count: int = 0

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"PersonalMovieRecommender/{settings.VERSION}",
        }
        if self.client_id:
            headers["simkl-api-key"] = self.client_id
        if self.user_token:
            headers["Authorization"] = f"Bearer {self.user_token}"
        return headers

    async def _throttle(self, method: str) -> None:
        """Enforces rate limiting between consecutive calls."""
        now = time.monotonic()
        if method.upper() == "GET":
            elapsed = now - self._last_get_time
            if elapsed < self._min_get_interval:
                await asyncio.sleep(self._min_get_interval - elapsed)
            self._last_get_time = time.monotonic()
        elif method.upper() == "POST":
            elapsed = now - self._last_post_time
            if elapsed < self._min_post_interval:
                await asyncio.sleep(self._min_post_interval - elapsed)
            self._last_post_time = time.monotonic()

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = self._get_headers()

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            await self._throttle(method)
            try:
                async with httpx.AsyncClient(
                    transport=self.transport,
                    timeout=self.timeout,
                ) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        params=params,
                        json=json_data,
                    )

                if response.status_code in (200, 201):
                    if not response.content:
                        return {}
                    return response.json()

                if response.status_code in (401, 403):
                    msg = f"Simkl auth failed (HTTP {response.status_code}): {response.text}"
                    raise SimklAuthError(msg)

                if response.status_code == 429:
                    logger.warning(
                        "Simkl rate limit exceeded (HTTP 429). Attempt %d/%d",
                        attempt + 1,
                        self.max_retries,
                    )
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(1.5 * (2**attempt))
                        continue
                    raise SimklRateLimitError("Simkl rate limit exceeded after retries")

                if response.status_code >= 500:
                    logger.warning(
                        "Simkl upstream error (HTTP %d). Attempt %d/%d",
                        response.status_code,
                        attempt + 1,
                        self.max_retries,
                    )
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(1.0 * (2**attempt))
                        continue
                    raise SimklUpstreamError(
                        f"Simkl upstream server error: HTTP {response.status_code}",
                        status_code=response.status_code,
                    )

                raise SimklError(
                    f"Simkl request failed with HTTP {response.status_code}: {response.text}",
                    status_code=response.status_code,
                )

            except httpx.TimeoutException as e:
                logger.warning(
                    "Simkl request timeout on %s. Attempt %d/%d",
                    path,
                    attempt + 1,
                    self.max_retries,
                )
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1.0 * (2**attempt))
                    continue
                raise SimklUpstreamError(f"Simkl request timed out: {e}") from e

            except httpx.RequestError as e:
                logger.warning(
                    "Simkl connection error on %s. Attempt %d/%d",
                    path,
                    attempt + 1,
                    self.max_retries,
                )
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1.0 * (2**attempt))
                    continue
                raise SimklUpstreamError(f"Simkl connection failed: {e}") from e

        if last_error:
            raise SimklUpstreamError(f"Simkl request failed: {last_error}") from last_error

    async def get_user_settings(self) -> Dict[str, Any]:
        """Fetches authenticated user profile and settings from Simkl."""
        return await self._request("GET", "/users/settings")

    async def get_activities(self) -> Dict[str, Any]:
        """Fetches user activity timestamps to detect changes since last sync."""
        return await self._request("GET", "/sync/activities")

    async def get_items(
        self,
        media_type: str,
        date_from: Optional[datetime | str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetches user items (watched, plan to watch, hold, dropped) for movies or shows.
        Optionally filters items changed since `date_from`.
        """
        if media_type not in ("movies", "shows"):
            raise ValueError(f"Invalid media_type '{media_type}'. Must be 'movies' or 'shows'.")

        params: Dict[str, str] = {}
        if date_from:
            if isinstance(date_from, datetime):
                # Ensure UTC format YYYY-MM-DDTHH:MM:SSZ
                if date_from.tzinfo is None:
                    date_from = date_from.replace(tzinfo=timezone.utc)
                params["date_from"] = date_from.strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                params["date_from"] = str(date_from)

        path = f"/sync/all-items/{media_type}"
        data = await self._request("GET", path, params=params)

        if isinstance(data, dict):
            return data.get(media_type, [])
        if isinstance(data, list):
            return data
        return []

    async def add_to_list(
        self,
        media_type: str,
        items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Adds approved items to a Simkl list (default: plantowatch).
        SAFETY INVARIANT: write_calls_count is incremented to track write operations.
        """
        if media_type not in ("movies", "shows"):
            raise ValueError(f"Invalid media_type '{media_type}'. Must be 'movies' or 'shows'.")

        self.write_calls_count += 1
        payload = {media_type: items}
        return await self._request("POST", "/sync/add-to-list", json_data=payload)
