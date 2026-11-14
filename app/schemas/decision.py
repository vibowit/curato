from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.sync import SimklWriteItemResult

DecisionType = Literal["accept", "reject", "seen", "later"]


class SingleDecisionRequest(BaseModel):
    """Payload to record a decision for a single recommendation."""

    recommendation_id: int = Field(..., description="ID of the recommendation")
    decision: DecisionType = Field(
        ..., description="User decision: 'accept', 'reject', 'seen', 'later'"
    )
    note: Optional[str] = Field(default=None, description="Optional note from the user")


class DecisionBatchRequest(BaseModel):
    """Payload to record decisions for one or more recommendations."""

    decisions: List[SingleDecisionRequest] = Field(
        ..., min_length=1, description="List of decisions to apply"
    )


class UserDecisionRead(BaseModel):
    """Read schema for recorded user decision."""

    id: int
    recommendation_id: int
    decision: str
    created_at: datetime
    note: Optional[str] = None
    media_title: Optional[str] = None
    media_year: Optional[int] = None
    media_type: Optional[str] = None

    model_config = {"from_attributes": True}


class DecisionBatchResponse(BaseModel):
    """Response returned after processing a batch of user decisions."""

    processed_count: int
    decisions: List[UserDecisionRead]


class ApproveBatchRequest(BaseModel):
    """Request payload to bulk-approve recommendations and add them to Simkl."""

    recommendation_ids: List[int] = Field(
        ..., min_length=1, description="List of recommendation IDs to add to Simkl"
    )


class ApproveBatchResponse(BaseModel):
    """Response returned after bulk approving and adding items to Simkl."""

    total_requested: int
    added_count: int
    already_added_count: int
    failed_count: int
    items: List[SimklWriteItemResult]
