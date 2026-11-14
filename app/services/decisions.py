import logging
from typing import List, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundException
from app.models.base import utc_now
from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.models.recommendation import Recommendation, UserDecision
from app.schemas.decision import DecisionBatchRequest, DecisionBatchResponse, UserDecisionRead

logger = logging.getLogger(__name__)


class DecisionService:
    """Domain service for managing and recording user decisions on recommendations."""

    def __init__(self, db_session: Session):
        self.db = db_session

    def record_decisions(self, request: DecisionBatchRequest) -> DecisionBatchResponse:
        """
        Records user decisions ('accept', 'reject', 'seen', 'later') for recommendations.

        Effects:
        - 'accept': sets Recommendation.status to 'accepted'.
        - 'reject': sets Recommendation.status to 'rejected'.
        - 'seen': sets Recommendation.status to 'seen' and updates WatchHistory to 'completed'.
        - 'later': sets Recommendation.status to 'pending'.
        - All decisions are recorded as audit entries in UserDecision.
        """
        recorded_reads: List[UserDecisionRead] = []
        now = utc_now()

        for item in request.decisions:
            rec = self.db.get(Recommendation, item.recommendation_id)
            if not rec:
                raise NotFoundException(
                    f"Recommendation with ID {item.recommendation_id} not found."
                )

            media = self.db.get(MediaItem, rec.media_item_id)

            # Map decision to recommendation status
            if item.decision == "accept":
                rec.status = "accepted"
            elif item.decision == "reject":
                rec.status = "rejected"
            elif item.decision == "seen":
                rec.status = "seen"
                # Mark as watched/completed in local watch history
                if media:
                    history = self.db.scalar(
                        select(WatchHistory).where(WatchHistory.media_item_id == media.id)
                    )
                    if not history:
                        history = WatchHistory(
                            media_item_id=media.id,
                            status="completed",
                            synced_at=now,
                        )
                        self.db.add(history)
                    else:
                        history.status = "completed"
                        history.synced_at = now
            elif item.decision == "later":
                rec.status = "pending"

            # Create decision audit log entry
            user_decision = UserDecision(
                recommendation_id=rec.id,
                decision=item.decision,
                note=item.note,
                created_at=now,
            )
            self.db.add(user_decision)
            self.db.flush()

            recorded_reads.append(
                UserDecisionRead(
                    id=user_decision.id,
                    recommendation_id=rec.id,
                    decision=user_decision.decision,
                    created_at=user_decision.created_at,
                    note=user_decision.note,
                    media_title=media.title if media else None,
                    media_year=media.year if media else None,
                    media_type=media.media_type if media else None,
                )
            )

        self.db.commit()
        logger.info("Successfully recorded %d user decisions", len(recorded_reads))

        return DecisionBatchResponse(
            processed_count=len(recorded_reads),
            decisions=recorded_reads,
        )

    def list_decisions(
        self,
        limit: int = 50,
        offset: int = 0,
        decision_filter: Optional[str] = None,
    ) -> List[UserDecisionRead]:
        """Lists historical user decisions with media details."""
        stmt = (
            select(UserDecision, MediaItem)
            .join(Recommendation, UserDecision.recommendation_id == Recommendation.id)
            .outerjoin(MediaItem, Recommendation.media_item_id == MediaItem.id)
            .order_by(desc(UserDecision.created_at))
        )

        if decision_filter:
            stmt = stmt.where(UserDecision.decision == decision_filter)

        stmt = stmt.offset(offset).limit(limit)
        rows = self.db.execute(stmt).all()

        results: List[UserDecisionRead] = []
        for decision_row, media_row in rows:
            results.append(
                UserDecisionRead(
                    id=decision_row.id,
                    recommendation_id=decision_row.recommendation_id,
                    decision=decision_row.decision,
                    created_at=decision_row.created_at,
                    note=decision_row.note,
                    media_title=media_row.title if media_row else None,
                    media_year=media_row.year if media_row else None,
                    media_type=media_row.media_type if media_row else None,
                )
            )

        return results
