"""Pydantic schemas for AI product metadata generation API."""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class AIGenerationTriggerResponse(BaseModel):
    """Response returned immediately when an AI generation job is initiated."""
    model_config = ConfigDict(from_attributes=True)

    generation_id: int = Field(..., description="Unique ID of the created generation run.")
    product_id: int = Field(..., description="ID of the target product.")
    status: str = Field(..., description="Initial generation status (pending).")


class AIGenerationStatusResponse(BaseModel):
    """Detailed response for querying generation status and AI output."""
    model_config = ConfigDict(from_attributes=True)

    generation_id: int = Field(..., description="Unique ID of the generation run.")
    product_id: int = Field(..., description="ID of the target product.")
    generation_number: int = Field(..., description="Sequential run number for this product.")
    status: str = Field(..., description="Lifecycle status: pending, processing, completed, or failed.")
    output: Optional[dict[str, Any]] = Field(None, description="Structured AI metadata payload upon completion.")
    acceptance_state: Optional[dict[str, Any]] = Field(None, description="Field-level seller acceptance review state.")
    processing_time: Optional[float] = Field(None, description="Inference and processing latency in seconds.")
    error_message: Optional[str] = Field(None, description="Diagnostic error details if generation failed.")
    started_at: Optional[datetime] = Field(None, description="Timestamp when processing began.")
    completed_at: Optional[datetime] = Field(None, description="Timestamp when processing finished.")
    created_at: Optional[datetime] = Field(None, description="Timestamp when generation record was created.")
