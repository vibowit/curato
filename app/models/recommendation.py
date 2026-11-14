from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.media import MediaItem


class RecommendationRun(Base):
    """Tracks a recommendation generation batch run."""

    __tablename__ = "recommendation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending, completed, failed
    profile_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    parameters_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    recommendations: Mapped[List["Recommendation"]] = relationship(
        "Recommendation", back_populates="run", cascade="all, delete-orphan"
    )


class Recommendation(Base):
    """Stores an individual recommended item within a run."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("recommendation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    media_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    positive_factors_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risks_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending, accepted, rejected, seen, added, error
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    run: Mapped["RecommendationRun"] = relationship(
        "RecommendationRun", back_populates="recommendations"
    )
    media_item: Mapped["MediaItem"] = relationship("MediaItem", back_populates="recommendations")
    decisions: Mapped[List["UserDecision"]] = relationship(
        "UserDecision", back_populates="recommendation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("run_id", "media_item_id", name="uq_recommendations_run_media"),
    )


class UserDecision(Base):
    """Stores user interaction/decision for a recommendation."""

    __tablename__ = "user_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recommendations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(50), nullable=False)  # accept, reject, seen, later
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    recommendation: Mapped["Recommendation"] = relationship(
        "Recommendation", back_populates="decisions"
    )
