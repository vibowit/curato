from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CandidateItem(BaseModel):
    """Normalized candidate item fetched from TMDB or external sources."""

    tmdb_id: int
    media_type: str = Field(..., description="'movie' or 'show'")
    title: str
    year: Optional[int] = None
    overview: Optional[str] = None
    genres: List[str] = Field(default_factory=list)
    genre_ids: List[int] = Field(default_factory=list)
    director_or_creator: Optional[str] = None
    vote_average: float = 0.0
    vote_count: int = 0
    popularity: float = 0.0
    poster_path: Optional[str] = None
    imdb_id: Optional[str] = None
    source_strategy: str = Field(
        ..., description="e.g. 'similar_to_favorites', 'profile_genres', 'director', 'exploration'"
    )


class LLMRecommendationEvaluation(BaseModel):
    """Evaluation result from LLM for a single candidate."""

    candidate_index: int = Field(..., description="Index of the candidate from the input batch")
    match_score: float = Field(..., ge=0.0, le=100.0, description="Heuristic score from 0 to 100")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence based on data completeness (0.0 to 1.0)"
    )
    positive_factors: List[str] = Field(
        default_factory=list, description="Key factors contributing to the match"
    )
    risks: List[str] = Field(
        default_factory=list, description="Potential mismatches or user concerns"
    )
    reason: str = Field(..., description="Concise narrative justification for the user")


class LLMEvaluationBatchResponse(BaseModel):
    """Batch response structure expected from LLM."""

    evaluations: List[LLMRecommendationEvaluation] = Field(default_factory=list)


class RecommendationRunCreateRequest(BaseModel):
    """Request payload to trigger a new recommendation run."""

    movie_limit: int = Field(
        default=10, ge=1, le=50, description="Target number of movie recommendations"
    )
    show_limit: int = Field(
        default=5, ge=1, le=25, description="Target number of show recommendations"
    )
    mode: str = Field(default="weekly", description="Generation mode: 'weekly', 'ondemand', etc.")
    exclude_genres: List[str] = Field(
        default_factory=list, description="Additional genres to exclude (e.g. ['Animation'])"
    )
    force_profile_version: Optional[str] = Field(
        default=None, description="Optional specific taste profile version to use instead of active"
    )


class MediaItemSummary(BaseModel):
    """Summary of media item metadata for recommendation outputs."""

    id: int
    media_type: str
    title: str
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    simkl_id: Optional[int] = None
    imdb_id: Optional[str] = None
    metadata_json: Optional[str] = None
    poster_path: Optional[str] = None

    model_config = {"from_attributes": True}


class RecommendationRead(BaseModel):
    """Schema for individual recommendation output."""

    id: int
    run_id: int
    media_item_id: int
    match_score: float
    confidence: float
    reason: str
    positive_factors: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    status: str
    latest_decision: Optional[str] = None
    created_at: datetime
    media_item: Optional[MediaItemSummary] = None

    model_config = {"from_attributes": True}


class RecommendationRunRead(BaseModel):
    """Detailed response for a recommendation run with all its items."""

    id: int
    status: str
    created_at: datetime
    profile_version: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    summary: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    recommendations: List[RecommendationRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class RecommendationRunSummary(BaseModel):
    """Summary item for listing historical recommendation runs."""

    id: int
    status: str
    created_at: datetime
    profile_version: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    summary: Optional[str] = None
    recommendations_count: int = 0

    model_config = {"from_attributes": True}
