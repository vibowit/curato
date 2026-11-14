from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.history import WatchHistory
    from app.models.recommendation import Recommendation


class MediaItem(Base, TimestampMixin):
    """Represents a movie or TV show with external identifiers and metadata."""

    __tablename__ = "media_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "movie" | "show"
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # External identifiers
    tmdb_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    simkl_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    imdb_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    watch_history: Mapped[List["WatchHistory"]] = relationship(
        "WatchHistory", back_populates="media_item", cascade="all, delete-orphan"
    )
    recommendations: Mapped[List["Recommendation"]] = relationship(
        "Recommendation", back_populates="media_item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_media_items_type_simkl", "media_type", "simkl_id"),
        Index("ix_media_items_type_tmdb", "media_type", "tmdb_id"),
        Index("ix_media_items_type_title_year", "media_type", "title", "year"),
    )
