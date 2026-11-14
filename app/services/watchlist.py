import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import (
    AppException,
    AuthRequiredException,
    InvalidStateException,
    NotFoundException,
    RateLimitedException,
    UpstreamErrorException,
)
from app.integrations.simkl import SimklClient, SimklError
from app.models.base import utc_now
from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.models.recommendation import Recommendation
from app.schemas.sync import SimklWriteItemResult

logger = logging.getLogger(__name__)


class WatchlistService:
    """
    Domain service for securely and idempotently adding approved titles
    to the user's Simkl watchlist (Plan to Watch).
    """

    def __init__(self, db_session: Session, simkl_client: Optional[SimklClient] = None):
        self.db = db_session
        self.simkl_client = simkl_client or SimklClient()

    async def add_approved_recommendation(self, recommendation_id: int) -> SimklWriteItemResult:
        """
        Adds an approved recommendation to Simkl watchlist.

        SAFETY INVARIANTS:
        1. Explicit user approval is strictly required (status must be 'accepted').
        2. Idempotent: repeated calls do not produce duplicate writes or errors.
        """
        rec = self.db.get(Recommendation, recommendation_id)
        if not rec:
            raise NotFoundException(f"Recommendation with ID {recommendation_id} not found.")

        # Invariant 1: Block write if item was already added (Idempotency)
        if rec.status == "added":
            media = self.db.get(MediaItem, rec.media_item_id)
            title = media.title if media else "Unknown"
            logger.info(
                "Recommendation %d is already marked as added. Skipping Simkl write.",
                recommendation_id,
            )
            return SimklWriteItemResult(
                success=True,
                media_type=media.media_type if media else "movie",
                simkl_id=media.simkl_id if media else None,
                tmdb_id=media.tmdb_id if media else None,
                imdb_id=media.imdb_id if media else None,
                title=title,
                status="already_added",
                message="Item was already added to Simkl watchlist.",
            )

        # Invariant 2: Block write if not explicitly accepted
        if rec.status != "accepted":
            msg = (
                f"Cannot add recommendation {recommendation_id} to Simkl watchlist. "
                f"Current status is '{rec.status}'. Explicit user approval is required."
            )
            logger.warning(msg)
            raise InvalidStateException(msg)

        media = self.db.get(MediaItem, rec.media_item_id)
        if not media:
            raise NotFoundException(f"Media item with ID {rec.media_item_id} not found.")

        # Prepare Simkl payload
        plural_type = "movies" if media.media_type == "movie" else "shows"
        ids_dict = {}
        if media.simkl_id:
            ids_dict["simkl"] = media.simkl_id
        if media.tmdb_id:
            ids_dict["tmdb"] = media.tmdb_id
        if media.imdb_id:
            ids_dict["imdb"] = media.imdb_id

        simkl_item = {
            "title": media.title,
            "year": media.year,
            "ids": ids_dict,
            "to": "plantowatch",
        }

        try:
            resp = await self.simkl_client.add_to_list(media_type=plural_type, items=[simkl_item])

            # Update recommendation status
            rec.status = "added"

            # Update local watch history
            now = utc_now()
            history = self.db.scalar(
                select(WatchHistory).where(WatchHistory.media_item_id == media.id)
            )
            if not history:
                history = WatchHistory(
                    media_item_id=media.id,
                    status="plantowatch",
                    synced_at=now,
                )
                self.db.add(history)
            else:
                history.status = "plantowatch"
                history.synced_at = now

            self.db.commit()

            return SimklWriteItemResult(
                success=True,
                media_type=media.media_type,
                simkl_id=media.simkl_id,
                tmdb_id=media.tmdb_id,
                imdb_id=media.imdb_id,
                title=media.title,
                status="added",
                message="Successfully added to Simkl Plan to Watch.",
                simkl_response=resp,
            )

        except Exception as e:
            self.db.rollback()
            if isinstance(e, SimklError):
                if e.code == "AUTH_REQUIRED":
                    raise AuthRequiredException(message=e.message) from e
                if e.code == "RATE_LIMITED":
                    raise RateLimitedException(message=e.message) from e
                raise UpstreamErrorException(message=e.message) from e
            if isinstance(e, AppException):
                raise e
            raise UpstreamErrorException(f"Failed to write to Simkl watchlist: {e}") from e
