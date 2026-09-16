"""Pydantic schemas and DTO contracts for Step 07.1 Retrieval Evaluation Subsystem.

Implements Q65–Q70:
- BenchmarkCase and BenchmarkSuite (Q66, Q68)
- NormalizedSearchResult (Q70)
- QueryEvaluationResult and MetricSummary (Q65)
- QueryTypeBreakdown across 5 archetypes (Q68)
- EvaluationRun with live provenance and catalog limitations (Q69)
"""

from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.product import ProductResponse
from app.schemas.search import SearchFilters


QueryArchetype = Literal[
    "exact_attribute",
    "compound_constraints",
    "semantic_intent",
    "edge_cases",
    "zero_result"
]

BenchmarkTrack = Literal["curated", "synthetic"]
BenchmarkTier = Literal["smoke", "standard", "extended"]
TargetMode = Literal["service", "api"]


class BenchmarkCase(BaseModel):
    """Single test query definition with ground truth and expected constraints (Q66, Q67).
    
    Ground truth remains strictly immutable during evaluation.
    """
    model_config = ConfigDict(extra="forbid")

    benchmark_id: str = Field(..., description="Unique identifier for benchmark case.")
    query_text: str = Field(..., min_length=1, description="Raw query string to evaluate.")
    track: BenchmarkTrack = Field(..., description="Query provenance track: curated vs synthetic.")
    query_type: QueryArchetype = Field(..., description="Query archetype for diagnostic partitioning.")
    expected_constraints: SearchFilters = Field(
        default_factory=SearchFilters,
        description="Explicit structured filters expected for this query."
    )
    ground_truth: dict[int, int] = Field(
        default_factory=dict,
        description="Immutable mapping of product_id -> relevance_grade (2=high, 1=partial, 0=irrelevant)."
    )
    is_zero_result_expected: bool = Field(
        default=False,
        description="Whether query is expected to return 0 results (e.g., out-of-catalog or negative query)."
    )
    limit: Optional[int] = Field(default=20, ge=1, le=100, description="Requested top N results.")


class BenchmarkSuite(BaseModel):
    """Collection of benchmark cases forming a versioned suite (Q68)."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Suite name (e.g., smoke, standard).")
    version: str = Field(default="1.0.0", description="Semantic version of the suite.")
    tier: BenchmarkTier = Field(..., description="Execution tier.")
    cases: list[BenchmarkCase] = Field(default_factory=list, description="List of benchmark cases.")


class NormalizedSearchResult(BaseModel):
    """Target-agnostic normalized representation of a single search result (Q70)."""
    model_config = ConfigDict(from_attributes=True)

    product_id: int = Field(..., description="Product ID.")
    score: float = Field(..., description="Hybrid ranking score.")
    rank: int = Field(..., ge=1, description="1-based position in results.")
    match_reasons: list[str] = Field(default_factory=list, description="Match signals.")
    product: Optional[ProductResponse] = Field(default=None, description="Product entity if available.")


class QueryEvaluationResult(BaseModel):
    """Detailed evaluation result for a single benchmark query (Q65, Q68)."""
    model_config = ConfigDict(extra="forbid")

    benchmark_id: str = Field(..., description="Benchmark case ID.")
    query_text: str = Field(..., description="Input query.")
    track: BenchmarkTrack = Field(..., description="Track.")
    query_type: QueryArchetype = Field(..., description="Query archetype.")
    returned_count: int = Field(..., description="Number of products returned.")
    recall_at_k: dict[str, float] = Field(
        default_factory=dict,
        description="Recall@K for mysql, faiss, and union candidates."
    )
    hit_rate_at_10: float = Field(default=0.0, description="HitRate@10 (1.0 if any relevant in top 10).")
    ndcg_at_10: Optional[float] = Field(default=None, description="NDCG@10 (None for zero-result queries).")
    ndcg_at_20: Optional[float] = Field(default=None, description="NDCG@20 (None for zero-result queries).")
    mrr: Optional[float] = Field(default=None, description="MRR (None for zero-result queries).")
    hard_filter_violations: int = Field(
        default=0,
        description="Count of returned products violating explicit hard constraints."
    )
    zero_result_correct: Optional[bool] = Field(
        default=None,
        description="True if zero-result query returned 0 products, False if false positives returned."
    )
    k_expanded: bool = Field(default=False, description="Whether bounded K expansion triggered.")
    latency_ms: float = Field(..., description="Measured latency in milliseconds.")
    error: Optional[str] = Field(default=None, description="Execution error message if failed.")


class QueryTypeBreakdown(BaseModel):
    """Partitioned evaluation statistics for a query archetype (Q68)."""
    model_config = ConfigDict(extra="forbid")

    query_count: int = Field(..., description="Number of queries in this archetype.")
    mean_ndcg_at_10: Optional[float] = Field(default=None, description="Mean NDCG@10.")
    mean_ndcg_at_20: Optional[float] = Field(default=None, description="Mean NDCG@20.")
    mean_mrr: Optional[float] = Field(default=None, description="Mean MRR.")
    mean_union_recall: Optional[float] = Field(default=None, description="Mean union Recall@K.")
    hard_filter_violations: int = Field(default=0, description="Total hard filter violations.")
    zero_result_accuracy: Optional[float] = Field(default=None, description="Zero result accuracy if applicable.")


class MetricSummary(BaseModel):
    """Global aggregate metrics across an entire evaluation run (Q65).
    
    All metrics retain their distinct diagnostic meaning.
    """
    model_config = ConfigDict(extra="forbid")

    total_queries: int = Field(..., description="Total evaluated queries.")
    successful_queries: int = Field(..., description="Successfully executed queries.")
    failed_queries: int = Field(default=0, description="Queries that threw runtime errors.")
    ndcg_at_10: float = Field(..., description="Macro-averaged NDCG@10 across eligible queries.")
    ndcg_at_20: float = Field(..., description="Macro-averaged NDCG@20 across eligible queries.")
    mrr: float = Field(..., description="Macro-averaged MRR across eligible queries.")
    candidate_recall_mysql: float = Field(..., description="Mean MySQL candidate recall.")
    candidate_recall_faiss: float = Field(..., description="Mean FAISS candidate recall.")
    candidate_recall_union: float = Field(..., description="Mean union candidate recall.")
    hit_rate_at_10: float = Field(..., description="Proportion of queries with >=1 relevant item in top 10.")
    hard_filter_violation_rate: float = Field(
        ...,
        description="Violation rate across all returned products. MUST BE 0.0 for passing gate."
    )
    total_hard_filter_violations: int = Field(..., description="Total violation count.")
    k_expansion_rate: float = Field(..., description="Proportion of queries triggering K expansion.")
    latency_p50_ms: float = Field(..., description="P50 latency in ms.")
    latency_p95_ms: float = Field(..., description="P95 latency in ms.")
    latency_p99_ms: float = Field(..., description="P99 latency in ms.")


class CatalogLimitations(BaseModel):
    """Honest catalog limitations and statistical significance disclosure (Repair 3)."""
    model_config = ConfigDict(extra="forbid")

    active_product_count: int = Field(..., description="Count of active products in catalog.")
    statistical_significance: Literal["HIGH", "MODERATE", "LOW"] = Field(
        ...,
        description="Assessment of statistical validity of metrics based on catalog size."
    )
    notice: str = Field(..., description="Human-readable limitation notice.")


class EvaluationRun(BaseModel):
    """Immutable versioned evaluation artifact capturing complete provenance and results (Q69)."""
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., description="Unique timestamped run identifier.")
    timestamp: str = Field(..., description="ISO 8601 execution timestamp.")
    benchmark_name: str = Field(..., description="Name of the benchmark suite.")
    benchmark_tier: BenchmarkTier = Field(..., description="Tier (smoke, standard, extended).")
    target: TargetMode = Field(..., description="Execution target (service vs api).")
    system_configuration: dict[str, Any] = Field(
        ...,
        description="Live introspected system configuration (weights, models, limits)."
    )
    catalog_limitations: CatalogLimitations = Field(
        ...,
        description="Honest reporting of catalog limitations."
    )
    correctness_gate_passed: bool = Field(
        ...,
        description="True if and only if hard_filter_violation_rate == 0.0% and failed_queries == 0."
    )
    summary_metrics: MetricSummary = Field(..., description="Aggregate evaluation metrics.")
    query_type_breakdown: dict[str, QueryTypeBreakdown] = Field(
        default_factory=dict,
        description="Metrics partitioned by query archetype."
    )
    query_results: list[QueryEvaluationResult] = Field(
        default_factory=list,
        description="Detailed per-query results for regression analysis."
    )
