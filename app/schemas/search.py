"""Pydantic schemas and DTO contracts for Phase 07 Hybrid Search.

Implements Q56, Q58, Q59, Q62:
- Typed SearchQuery and SearchFilters
- SearchResultItem with normalized hybrid score [0, 1] and match reasons
- SearchMetadata with telemetry and parsed understanding
- SearchResponse and optional debug diagnostics
- Typed HybridSearchConfig
"""

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.product import ProductResponse


class SearchFilters(BaseModel):
    """Structured constraints extracted from the user's query or passed explicitly.
    
    Supports the Core 6 e-commerce filters (Q63).
    """
    model_config = ConfigDict(extra="forbid")

    brand: Optional[str] = Field(default=None, description="Exact or normalized brand name.")
    category: Optional[str] = Field(default=None, description="Category name extracted from query.")
    category_id: Optional[int] = Field(default=None, description="Resolved database category ID.")
    color: Optional[str] = Field(default=None, description="Product color attribute.")
    size: Optional[str] = Field(default=None, description="Product size attribute.")
    min_price: Optional[float] = Field(default=None, ge=0, description="Minimum price bound.")
    max_price: Optional[float] = Field(default=None, ge=0, description="Maximum price bound.")


class SearchQuery(BaseModel):
    """Contract between Query Understanding and the Retrieval Layer (Q56)."""
    model_config = ConfigDict(extra="forbid")

    original_query: str = Field(..., min_length=1, description="Raw input search query.")
    semantic_query: str = Field(..., description="Residual query text stripped of structured filter tokens.")
    filters: SearchFilters = Field(default_factory=SearchFilters, description="Structured filters.")


class HybridSearchConfig(BaseModel):
    """Typed configuration boundary for hybrid search (Q58, Q59, Q60)."""
    model_config = ConfigDict(extra="forbid")

    mysql_candidate_k: int = Field(default=100, ge=1, le=500, description="MySQL candidate retrieval pool size.")
    faiss_candidate_k: int = Field(default=100, ge=1, le=500, description="FAISS candidate retrieval pool size.")
    max_candidate_k: int = Field(default=300, ge=10, le=1000, description="Maximum candidate pool during bounded expansion.")
    default_limit: int = Field(default=20, ge=1, le=100, description="Default number of final results returned.")
    enable_expansion: bool = Field(default=True, description="Whether to trigger bounded expansion if eligible < limit.")
    semantic_weight: float = Field(default=0.65, ge=0.0, le=1.0, description="Weight for semantic vector similarity.")
    structured_weight: float = Field(default=0.35, ge=0.0, le=1.0, description="Weight for structured/lexical relevance.")


class SearchResultItem(BaseModel):
    """Individual ranked product item in search results (Q62)."""
    model_config = ConfigDict(from_attributes=True)

    product: ProductResponse = Field(..., description="Canonical product entity.")
    score: float = Field(..., ge=0.0, le=1.0, description="Normalized hybrid ranking score in range [0, 1].")
    match_reasons: list[str] = Field(default_factory=list, description="Deterministic match provenance signals.")


class SearchMetadata(BaseModel):
    """Observability, pagination, and diagnostic metadata (Q62).
    
    Semantics:
    `eligible_candidate_count` (and its alias `total_eligible`) represents the count of products
    passing the authoritative MySQL eligibility guard within the retrieved candidate pool (K).
    It deliberately avoids an expensive, unbounded full-catalog COUNT(*) scan.
    """
    model_config = ConfigDict(extra="forbid")

    eligible_candidate_count: int = Field(
        ...,
        description="Eligible products discovered and verified within the evaluated candidate pool."
    )
    total_eligible: int = Field(
        ...,
        description="Alias for eligible_candidate_count representing pool-scoped eligible candidates."
    )
    returned_count: int = Field(..., description="Count of products returned in this response.")
    requested_limit: int = Field(..., description="Result limit requested by caller.")
    took_ms: float = Field(..., description="Total execution time in milliseconds.")
    k_expanded: bool = Field(default=False, description="Whether bounded K expansion was triggered.")
    parsed_filters: SearchFilters = Field(..., description="Structured filters extracted from the query.")
    semantic_query: str = Field(..., description="Residual semantic query passed to the embedding engine.")


class SearchResponse(BaseModel):
    """Top-level response contract for GET /api/v1/search (Q62)."""
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., description="Original query string.")
    results: list[SearchResultItem] = Field(default_factory=list, description="Ranked list of matching products.")
    metadata: SearchMetadata = Field(..., description="Search execution metadata.")
    debug_diagnostics: Optional[dict[str, Any]] = Field(default=None, description="Optional diagnostic details when debug=true.")
