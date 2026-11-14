import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import (
    AppException,
    AuthRequiredException,
    RateLimitedException,
    UpstreamErrorException,
)
from app.integrations.simkl import SimklClient, SimklError
from app.models.base import utc_now
from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.models.sync import SyncState
from app.schemas.sync import SimklSyncResponse, SimklSyncStatusResponse

logger = logging.getLogger(__name__)


def parse_datetime(val: Any) -> Optional[datetime]:
    """Parses various datetime string formats from Simkl API to a timezone-aware UTC datetime."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)

    val_str = str(val).strip()
    # Normalize 'Z' to '+00:00'
    val_str = val_str.replace("Z", "+00:00")

    # Try standard ISO formats
    try:
        dt = datetime.fromisoformat(val_str)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # Try space-separated timestamp
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(val_str, fmt)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    logger.warning("Could not parse datetime string: %s", val)
    return None


class SyncService:
    """Domain service for synchronizing Simkl history and watchlists into SQLite."""

    def __init__(self, db_session: Session, simkl_client: Optional[SimklClient] = None):
        self.db = db_session
        self.simkl_client = simkl_client or SimklClient()

    def get_status(self) -> SimklSyncStatusResponse:
        """Retrieves the current synchronization state from the database."""
        state = self.db.scalar(select(SyncState).where(SyncState.provider == "simkl"))
        if not state:
            return SimklSyncStatusResponse(
                provider="simkl",
                status="idle",
                last_success_at=None,
                cursor_or_activity_state=None,
                error_summary=None,
            )
        return SimklSyncStatusResponse(
            provider="simkl",
            status=state.status,
            last_success_at=state.last_success_at,
            cursor_or_activity_state=state.cursor_or_activity_state,
            error_summary=state.error_summary,
        )

    async def sync_simkl(
        self,
        media_types: Optional[List[str]] = None,
        force_full: bool = False,
    ) -> SimklSyncResponse:
        """
        Executes synchronization from Simkl into SQLite.
        Supports full and incremental modes.
        """
        types_to_sync = media_types or ["movies", "shows"]

        # 1. Fetch or create SyncState
        state = self.db.scalar(select(SyncState).where(SyncState.provider == "simkl"))
        if not state:
            state = SyncState(provider="simkl", status="idle")
            self.db.add(state)
            self.db.flush()

        date_from: Optional[datetime] = None
        if not force_full and state.last_success_at:
            date_from = state.last_success_at

        state.status = "syncing"
        self.db.commit()

        movies_added = 0
        movies_updated = 0
        shows_added = 0
        shows_updated = 0

        try:
            for media_type in types_to_sync:
                items = await self.simkl_client.get_items(media_type, date_from=date_from)
                added, updated = self._process_items(media_type=media_type, raw_items=items)

                if media_type == "movies":
                    movies_added += added
                    movies_updated += updated
                elif media_type == "shows":
                    shows_added += added
                    shows_updated += updated

            # 2. Update SyncState on success
            now = utc_now()
            state.status = "idle"
            state.last_success_at = now
            state.error_summary = None
            self.db.commit()

            total_synced = movies_added + movies_updated + shows_added + shows_updated
            return SimklSyncResponse(
                status="completed",
                synced_at=now,
                movies_added=movies_added,
                movies_updated=movies_updated,
                shows_added=shows_added,
                shows_updated=shows_updated,
                total_synced=total_synced,
                message=f"Successfully synced {total_synced} items from Simkl.",
            )

        except Exception as e:
            self.db.rollback()
            # Try recording the failure in sync_state
            try:
                state_fail = self.db.scalar(select(SyncState).where(SyncState.provider == "simkl"))
                if state_fail:
                    state_fail.status = "failed"
                    state_fail.error_summary = str(e)
                    self.db.commit()
            except Exception as inner_e:
                logger.error("Failed to update sync_state on error: %s", inner_e)

            if isinstance(e, SimklError):
                if e.code == "AUTH_REQUIRED":
                    raise AuthRequiredException(message=e.message) from e
                if e.code == "RATE_LIMITED":
                    raise RateLimitedException(message=e.message) from e
                raise UpstreamErrorException(message=e.message) from e
            if isinstance(e, AppException):
                raise e
            raise UpstreamErrorException(message=f"Sync failed: {e}") from e

    def _process_items(self, media_type: str, raw_items: List[Dict[str, Any]]) -> Tuple[int, int]:
        """Processes and upserts raw Simkl items into MediaItem and WatchHistory tables."""
        singular_type = "movie" if media_type == "movies" else "show"
        added_count = 0
        updated_count = 0

        for raw in raw_items:
            norm = self._normalize_raw_item(raw)
            if not norm["title"]:
                continue

            media_item, created_media = self._find_or_create_media_item(
                media_type=singular_type,
                title=norm["title"],
                year=norm["year"],
                simkl_id=norm["simkl_id"],
                tmdb_id=norm["tmdb_id"],
                imdb_id=norm["imdb_id"],
                metadata=norm.get("metadata"),
            )

            is_new_history = self._upsert_watch_history(
                media_item=media_item,
                status=norm["status"] or "plantowatch",
                user_rating=norm["user_rating"],
                watched_at=norm["watched_at"],
            )

            if is_new_history:
                added_count += 1
            else:
                updated_count += 1

        self.db.flush()
        return added_count, updated_count

    @staticmethod
    def _normalize_raw_item(raw_item: Dict[str, Any]) -> Dict[str, Any]:
        """Extracts normalized fields from both flat and nested Simkl structures."""
        media = raw_item.get("movie") or raw_item.get("show") or raw_item.get("anime") or {}

        title = str(raw_item.get("title") or media.get("title") or "").strip()
        year = raw_item.get("year") or media.get("year")
        if isinstance(year, str) and year.isdigit():
            year = int(year)
        elif not isinstance(year, int):
            year = None

        ids = raw_item.get("ids") or media.get("ids") or {}
        simkl_id = ids.get("simkl")
        tmdb_id = ids.get("tmdb")
        imdb_id = ids.get("imdb")

        status = str(raw_item.get("status") or "").lower()
        # Normalise 'plan to watch' to 'plantowatch'
        if status in ("plan to watch", "plantowatch", "planned"):
            status = "plantowatch"

        user_rating = raw_item.get("user_rating")
        if user_rating is not None:
            try:
                user_rating = float(user_rating)
            except (ValueError, TypeError):
                user_rating = None

        watched_at = parse_datetime(raw_item.get("last_watched_at") or raw_item.get("watched_at"))

        return {
            "title": title,
            "year": year,
            "simkl_id": simkl_id,
            "tmdb_id": tmdb_id,
            "imdb_id": str(imdb_id) if imdb_id else None,
            "status": status,
            "user_rating": user_rating,
            "watched_at": watched_at,
            "metadata": {"simkl_raw": raw_item},
        }

    def _find_or_create_media_item(
        self,
        media_type: str,
        title: str,
        year: Optional[int],
        simkl_id: Optional[int],
        tmdb_id: Optional[int],
        imdb_id: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> Tuple[MediaItem, bool]:
        """Finds existing MediaItem by external identifiers or title+year, or creates a new one."""
        item: Optional[MediaItem] = None

        # 1. Lookup by external IDs
        if simkl_id:
            item = self.db.scalar(
                select(MediaItem).where(
                    MediaItem.media_type == media_type,
                    MediaItem.simkl_id == simkl_id,
                )
            )
        if not item and tmdb_id:
            item = self.db.scalar(
                select(MediaItem).where(
                    MediaItem.media_type == media_type,
                    MediaItem.tmdb_id == tmdb_id,
                )
            )
        if not item and imdb_id:
            item = self.db.scalar(
                select(MediaItem).where(
                    MediaItem.media_type == media_type,
                    MediaItem.imdb_id == imdb_id,
                )
            )

        # 2. Lookup by title + year
        if not item and title:
            query = select(MediaItem).where(
                MediaItem.media_type == media_type,
                MediaItem.title.ilike(title),
            )
            if year:
                query = query.where(MediaItem.year == year)
            item = self.db.scalar(query)

        created = False
        if not item:
            item = MediaItem(
                media_type=media_type,
                title=title,
                year=year,
                simkl_id=simkl_id,
                tmdb_id=tmdb_id,
                imdb_id=imdb_id,
                metadata_json=json.dumps(metadata) if metadata else None,
            )
            self.db.add(item)
            self.db.flush()
            created = True
        else:
            # Update any missing external IDs
            if simkl_id and not item.simkl_id:
                item.simkl_id = simkl_id
            if tmdb_id and not item.tmdb_id:
                item.tmdb_id = tmdb_id
            if imdb_id and not item.imdb_id:
                item.imdb_id = imdb_id
            if year and not item.year:
                item.year = year

        return item, created

    def _upsert_watch_history(
        self,
        media_item: MediaItem,
        status: str,
        user_rating: Optional[float],
        watched_at: Optional[datetime],
    ) -> bool:
        """
        Finds or creates WatchHistory for the media item.
        Returns True if created, False if updated.
        """
        history = self.db.scalar(
            select(WatchHistory).where(WatchHistory.media_item_id == media_item.id)
        )
        is_new = False
        now = utc_now()

        if not history:
            history = WatchHistory(
                media_item_id=media_item.id,
                status=status,
                user_rating=user_rating,
                watched_at=watched_at,
                synced_at=now,
            )
            self.db.add(history)
            is_new = True
        else:
            history.status = status
            if user_rating is not None:
                history.user_rating = user_rating
            if watched_at is not None:
                history.watched_at = watched_at
            history.synced_at = now

        return is_new
