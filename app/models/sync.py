from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SyncState(Base):
    """Tracks synchronization progress and status with external providers."""

    __tablename__ = "sync_state"

    provider: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g., "simkl"
    last_success_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cursor_or_activity_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="idle", nullable=False
    )  # idle, syncing, failed
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
