"""Pydantic schemas and DTO contracts for Phase 08 Hybrid Recommendation Engine.

Implements Q88, Q90, Q91, Q92, Q93:
- RecommendationCandidateSignals
- RecommendationConfig with configurable weights
- RecommendationItem with normalized score and explainable match reasons
- RecommendationMetadata and RecommendationResponse
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.product import ProductResponse


class RecommendationCandidateSignals(BaseModel):
    """Normalized constituent affinity signals in [0, 1] for a candidate."""
    model_config = ConfigDict(extra="forbid")

    semantic_similarity: float = Field(default=0.0, ge=0.0, le=1.0, description="FAISS cosine similarity [0, 1].")
    category_affinity: float = Field(default=0.0, ge=0.0, le=1.0, description="Category matching affinity [0, 1].")
    attribute_overlap: float = Field(default=0.0, ge=0.0, le=1.0, description="Accepted AI metadata attribute overlap [0, 1].")
    price_similarity: float = Field(default=0.0, ge=0.0, le=1.0, description="Relative price proximity [0, 1].")
    brand_affinity: float = Field(default=0.0, ge=0.0, le=1.0, description="Brand matching affinity [0, 1].")


class RecommendationConfig(BaseModel):
    """Typed configuration boundary for hybrid recommendation engine."""
    model_config = ConfigDict(extra="ignore")

    candidate_k: int = Field(default=50, ge=5, le=200, description="Candidate retrieval pool size per branch.")
    default_limit: int = Field(default=5, ge=1, le=50, description="Default number of recommendations returned.")
    max_limit: int = Field(default=20, ge=1, le=100, description="Maximum permitted recommendation limit.")

    # Configurable ranker weights (Q91)
    semantic_weight: float = Field(default=0.40, ge=0.0, le=1.0, description="Weight for FAISS semantic similarity.")
    category_weight: float = Field(default=0.25, ge=0.0, le=1.0, description="Weight for category affinity.")
    attribute_weight: float = Field(default=0.15, ge=0.0, le=1.0, description="Weight for structured attribute overlap.")
    price_weight: float = Field(default=0.10, ge=0.0, le=1.0, description="Weight for price proximity.")
    brand_weight: float = Field(default=0.10, ge=0.0, le=1.0, description="Weight for brand affinity.")

    # Diversity / deduplication threshold (Q92)
    similarity_dedup_threshold: float = Field(
        default=0.95,
        ge=0.5,
        le=1.0,
        description="Cosine similarity threshold above which near-duplicate items are suppressed."
    )


class RecommendationItem(BaseModel):
    """Individual recommended product item with normalized score and match reasons (Q93)."""
    model_config = ConfigDict(from_attributes=True)

    product: ProductResponse = Field(..., description="Canonical product details.")
    score: float = Field(..., ge=0.0, le=1.0, description="Normalized recommendation score in [0, 1].")
    match_reasons: list[str] = Field(default_factory=list, description="Deterministic, explainable match provenance.")


class RecommendationMetadata(BaseModel):
    """Observability and execution telemetry for recommendations (Q93)."""
    model_config = ConfigDict(extra="forbid")

    source_product_id: int = Field(..., description="ID of the product for which recommendations were generated.")
    evaluated_candidates: int = Field(..., description="Count of unique candidates evaluated through the pipeline.")
    returned_count: int = Field(..., description="Count of final recommendations returned.")
    took_ms: float = Field(..., description="Total execution time in milliseconds.")
    faiss_candidate_count: int = Field(default=0, description="Candidates retrieved from FAISS branch.")
    mysql_candidate_count: int = Field(default=0, description="Candidates retrieved from MySQL branch.")
    degraded_mode: bool = Field(default=False, description="True if one retrieval branch failed gracefully.")


class RecommendationResponse(BaseModel):
    """Top-level response contract for GET /api/v1/products/{id}/recommendations (Q93)."""
    model_config = ConfigDict(extra="forbid")

    source_product_id: int = Field(..., description="Source product ID.")
    recommendations: list[RecommendationItem] = Field(default_factory=list, description="Ranked recommendations.")
    metadata: RecommendationMetadata = Field(..., description="Execution telemetry metadata.")
