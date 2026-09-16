"""Structured Global API Error Schemas.

Phase 10: Unified error response model.
Ensures no internal stack traces, SQL, file paths, credentials, or provider internals leak to clients.
"""

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class APIErrorDetail(BaseModel):
    """Detailed error object returned in response body."""
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., description="High-level machine-readable error code (e.g. 'NOT_FOUND', 'VALIDATION_ERROR').")
    message: str = Field(..., description="Sanitized, human-readable error description.")
    request_id: str = Field(..., description="Unique request tracing ID.")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp of the error event.")
    details: Optional[list[dict[str, Any]]] = Field(default=None, description="Optional safe field-level validation errors.")


class APIErrorResponse(BaseModel):
    """Top-level structured global error envelope."""
    model_config = ConfigDict(extra="forbid")

    error: APIErrorDetail = Field(..., description="Unified error details.")
