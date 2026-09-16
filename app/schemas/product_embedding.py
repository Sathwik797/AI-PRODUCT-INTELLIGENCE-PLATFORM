"""Product Embedding Schemas & DTOs.

Phase 06: Strongly-typed contracts for embedding lifecycle, configuration, and responses.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EmbeddingStatus(str, Enum):
    """Lifecycle status of a product embedding in MySQL."""
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    READY = "READY"
    STALE = "STALE"
    FAILED = "FAILED"


class EmbeddingConfig(BaseModel):
    """Strongly-typed embedding pipeline configuration identifying the vector space."""
    model_config = ConfigDict(frozen=True)

    provider: str = Field(default="google", description="Underlying embedding provider name.")
    model: str = Field(default="gemini-embedding-001", description="Authoritative model name.")
    dimension: int = Field(default=768, description="Output dimensionality of vectors.")
    builder_version: str = Field(default="v1", description="EmbeddingTextBuilder version.")


class ProductEmbeddingResponse(BaseModel):
    """Read contract for product embedding relational metadata."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    vector_id: int
    content_hash: str
    embedding_model: str
    embedding_dimension: int
    builder_version: str
    status: EmbeddingStatus
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
