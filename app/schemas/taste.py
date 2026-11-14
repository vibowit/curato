from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WeightedFeature(BaseModel):
    """Represents a taste feature with decoupled preference weight and model confidence."""

    name: str = Field(..., description="Name or motif of the feature")
    weight: float = Field(..., ge=0.0, le=1.0, description="Preference weight from 0.0 to 1.0")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Model confidence based on data quality (0.0 to 1.0)"
    )
    note: Optional[str] = Field(default=None, description="Optional explanatory note")


class TasteProfileContent(BaseModel):
    """Structured taste profile content stored as JSON in the database."""

    summary: str = Field(..., description="Narrative summary of user taste and key tendencies")
    genres: List[WeightedFeature] = Field(
        default_factory=list, description="Preferred genres with weights and confidence"
    )
    themes: List[WeightedFeature] = Field(
        default_factory=list, description="Recurring narrative themes, motifs, and tropes"
    )
    directors_or_creators: List[str] = Field(
        default_factory=list, description="Key favored directors, showrunners, or authors"
    )
    anti_preferences: List[str] = Field(
        default_factory=list, description="Disliked genres, tropes, or negative patterns"
    )
    temporary_interests: List[WeightedFeature] = Field(
        default_factory=list,
        description="Short-term or transient interests distinct from long-term taste",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Generation metadata (model, counts, provider, etc.)"
    )


class TasteProfileRead(BaseModel):
    """Schema for returning taste profile with provenance and version metadata."""

    id: int
    version: str
    active: bool
    created_at: datetime
    based_on_sync_at: Optional[datetime] = None
    content: TasteProfileContent

    model_config = {"from_attributes": True}


class TasteProfileVersionSummary(BaseModel):
    """Summary of a taste profile version for listing and auditing history."""

    id: int
    version: str
    active: bool
    created_at: datetime
    based_on_sync_at: Optional[datetime] = None
    summary: Optional[str] = None


class TasteProfileUpdate(BaseModel):
    """Request payload for manual taste profile correction."""

    summary: Optional[str] = Field(default=None, description="Updated summary")
    genres: Optional[List[WeightedFeature]] = Field(default=None, description="Adjusted genres")
    themes: Optional[List[WeightedFeature]] = Field(default=None, description="Adjusted themes")
    directors_or_creators: Optional[List[str]] = Field(
        default=None, description="Adjusted directors or creators"
    )
    anti_preferences: Optional[List[str]] = Field(
        default=None, description="Adjusted anti-preferences"
    )
    temporary_interests: Optional[List[WeightedFeature]] = Field(
        default=None, description="Adjusted temporary interests"
    )
    change_note: Optional[str] = Field(
        default=None, description="User note explaining the rationale for this manual correction"
    )


class TasteProfileGenerateRequest(BaseModel):
    """Options for triggering profile analysis and generation."""

    min_rating_loved: float = Field(
        default=8.0, ge=1.0, le=10.0, description="Threshold for loved items"
    )
    max_rating_disliked: float = Field(
        default=5.0, ge=1.0, le=10.0, description="Threshold for disliked items"
    )
    include_plantowatch: bool = Field(
        default=True, description="Whether to include Plan to Watch items as weak signal"
    )
    limit_history_items: int = Field(
        default=150, ge=10, le=500, description="Maximum number of history items to feed to LLM"
    )
