from typing import Any, Optional

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standardized error contract per API_CONTRACTS.md."""

    error_code: str = Field(description="Stable error code (e.g. AUTH_REQUIRED, UPSTREAM_ERROR)")
    message: str = Field(description="Human-readable error description")
    request_id: Optional[str] = Field(default=None, description="Request correlation ID")
    details: Optional[Any] = Field(
        default=None, description="Detailed validation or context error info"
    )
