from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Schema for /api/health response."""

    status: str = Field(default="ok", description="Application status")
    version: str = Field(description="Application version")
    environment: str = Field(description="Active environment")
    database: str = Field(description="Database connectivity status: 'connected' | 'error'")
    timestamp: datetime = Field(description="Current UTC timestamp")
