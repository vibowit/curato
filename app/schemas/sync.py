from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SimklSyncRequest(BaseModel):
    """Request options for triggering Simkl synchronization."""

    media_types: List[Literal["movies", "shows"]] = Field(
        default=["movies", "shows"],
        description="Media types to synchronize from Simkl",
    )
    force_full: bool = Field(
        default=False,
        description="If True, ignores last activity cursor and performs a full synchronization",
    )


class SimklSyncResponse(BaseModel):
    """Response returned upon successful or completed synchronization."""

    status: str = Field(description="Sync result: completed, partial, or failed")
    synced_at: datetime = Field(description="Timestamp when the sync finished")
    movies_added: int = Field(default=0, description="New movies added to the local database")
    movies_updated: int = Field(default=0, description="Existing movies updated with new data")
    shows_added: int = Field(default=0, description="New shows added to the local database")
    shows_updated: int = Field(default=0, description="Existing shows updated with new data")
    total_synced: int = Field(default=0, description="Total items processed")
    message: str = Field(description="Human-readable result summary")


class SimklSyncStatusResponse(BaseModel):
    """Current state of Simkl synchronization."""

    provider: str = "simkl"
    status: str = Field(description="Current status: idle, syncing, failed")
    last_success_at: Optional[datetime] = None
    cursor_or_activity_state: Optional[str] = None
    error_summary: Optional[str] = None


class SimklWriteItemResult(BaseModel):
    """Result of writing an item to Simkl list."""

    success: bool
    media_type: str
    simkl_id: Optional[int] = None
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    title: str
    status: str
    message: str
    simkl_response: Optional[Dict[str, Any]] = None
