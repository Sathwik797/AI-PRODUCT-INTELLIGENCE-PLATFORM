"""Pydantic schemas and DTO contracts for Phase 09 System-wide Evaluation.

Implements Q94 (Layered System Evaluation) & Q95 (Hard Correctness Gates):
- HardCorrectnessGateResult: Strict non-negotiable gates (must be 0 violations to pass)
- IntegrationCheckSummary: Cross-service propagation checks (Scenarios A through F)
- SystemQualityMetrics: Component-level metrics reported independently (Search, RAG, Recs, Embeddings)
- SystemOperationalMetrics: Latency percentiles and reliability rates
- SystemEvaluationArtifact: Versioned immutable artifact representing full system health
"""

from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

EvaluationStatus = Literal["PASSED", "FAILED", "ERROR"]


# ==============================================================================
# HARD CORRECTNESS GATES (Q95)
# ==============================================================================

class HardGateViolationCounts(BaseModel):
    """Breakdown of hard invariant violations. All must be 0 for passing gate."""
    model_config = ConfigDict(extra="forbid")

    invalid_citations: int = Field(default=0, description="Hallucinated or invalid citation references.")
    hard_filter_violations: int = Field(default=0, description="Search constraint violations.")
    inactive_product_leaks: int = Field(default=0, description="Inactive/draft products returned in search, RAG, or recs.")
    unaccepted_metadata_leaks: int = Field(default=0, description="Rejected or unreviewed metadata used as truth.")
    recommendation_self_returns: int = Field(default=0, description="Products recommending themselves.")
    canonical_data_inconsistencies: int = Field(default=0, description="Mismatch between live MySQL and downstream context.")


class HardCorrectnessGateResult(BaseModel):
    """Overall outcome of the non-negotiable hard correctness gates."""
    model_config = ConfigDict(extra="forbid")

    passed: bool = Field(..., description="True if and only if total_violations == 0.")
    total_checks: int = Field(..., description="Total invariant checks executed.")
    total_violations: int = Field(..., description="Total violations detected across all gates.")
    violations: HardGateViolationCounts = Field(..., description="Detailed violation counts per gate.")
    failure_reasons: list[str] = Field(default_factory=list, description="Diagnostic reasons if gates failed.")


# ==============================================================================
# INTEGRATION / CROSS-SERVICE CHECKS (Scenarios A through F)
# ==============================================================================

class ScenarioCheckDetail(BaseModel):
    """Outcome for a single cross-subsystem propagation scenario."""
    model_config = ConfigDict(extra="forbid")

    scenario_name: str = Field(..., description="Scenario identifier (A through F).")
    description: str = Field(..., description="Human-readable scenario description.")
    passed: bool = Field(..., description="True if scenario integrity held across all boundaries.")
    checks_performed: int = Field(default=0, description="Count of assertions in this scenario.")
    violations: list[str] = Field(default_factory=list, description="Specific discrepancies detected.")


class SystemIntegrationSummary(BaseModel):
    """Summary of all 6 cross-system integration scenarios."""
    model_config = ConfigDict(extra="forbid")

    all_passed: bool = Field(..., description="True if all integration scenarios passed.")
    scenarios: dict[str, ScenarioCheckDetail] = Field(
        default_factory=dict,
        description="Detailed outcome per scenario (scenario_a through scenario_f)."
    )


# ==============================================================================
# COMPONENT QUALITY METRICS (Reported Independently)
# ==============================================================================

class SearchQualityMetrics(BaseModel):
    """Retrieval & ranking quality metrics from search evaluation."""
    model_config = ConfigDict(extra="forbid")

    total_queries: int = Field(default=0)
    recall_at_10: Optional[float] = Field(default=None)
    hit_rate_at_10: Optional[float] = Field(default=None)
    ndcg_at_10: Optional[float] = Field(default=None)
    ndcg_at_20: Optional[float] = Field(default=None)
    mrr: Optional[float] = Field(default=None)
    hard_filter_violation_rate: float = Field(default=0.0)


class RAGQualityMetrics(BaseModel):
    """Grounding & citation metrics from RAG evaluation."""
    model_config = ConfigDict(extra="forbid")

    total_queries_evaluated: int = Field(default=0)
    citation_validity_rate: Optional[float] = Field(default=None, description="Proportion of valid citations.")
    grounded_claim_coverage: Optional[float] = Field(default=None, description="Proportion of factual claims backed by evidence.")
    schema_validity_rate: Optional[float] = Field(default=None, description="Proportion of model responses conforming to schema.")
    fallback_rate: float = Field(default=0.0, description="Proportion of queries triggering fail-closed fallback.")
    zero_result_accuracy: Optional[float] = Field(default=None, description="Accuracy of zero-result short circuiting.")


class RecommendationQualityMetrics(BaseModel):
    """Affinity and diversity metrics from recommendation evaluation."""
    model_config = ConfigDict(extra="forbid")

    total_evaluations: int = Field(default=0)
    eligible_candidate_coverage: Optional[float] = Field(default=None)
    mean_recommendation_score: Optional[float] = Field(default=None)
    duplicate_suppression_count: int = Field(default=0)
    self_return_rate: float = Field(default=0.0, description="Must be 0.0.")


class EmbeddingQualityMetrics(BaseModel):
    """Vector & lifecycle consistency metrics."""
    model_config = ConfigDict(extra="forbid")

    total_embeddings: int = Field(default=0)
    ready_count: int = Field(default=0)
    pending_or_stale_count: int = Field(default=0)
    hash_consistency_rate: Optional[float] = Field(default=None, description="Document hash vs content match rate.")
    vector_store_sync_rate: Optional[float] = Field(default=None, description="Proportion of READY embeddings present in FAISS.")


class SystemQualityMetrics(BaseModel):
    """Layer 1: Independent component quality metrics (no artificial blended score)."""
    model_config = ConfigDict(extra="forbid")

    search: SearchQualityMetrics = Field(default_factory=SearchQualityMetrics)
    rag: RAGQualityMetrics = Field(default_factory=RAGQualityMetrics)
    recommendations: RecommendationQualityMetrics = Field(default_factory=RecommendationQualityMetrics)
    embeddings: EmbeddingQualityMetrics = Field(default_factory=EmbeddingQualityMetrics)


# ==============================================================================
# OPERATIONAL METRICS
# ==============================================================================

class LatencyPercentiles(BaseModel):
    """P50, P95, and P99 latency measurements in milliseconds."""
    model_config = ConfigDict(extra="forbid")

    p50_ms: float = Field(default=0.0)
    p95_ms: float = Field(default=0.0)
    p99_ms: float = Field(default=0.0)
    mean_ms: float = Field(default=0.0)


class RAGLatencyDecomposition(BaseModel):
    """Stage-level latency breakdown for RAG operations."""
    model_config = ConfigDict(extra="forbid")

    retrieval_mean_ms: float = Field(default=0.0)
    llm_mean_ms: float = Field(default=0.0)
    validation_mean_ms: float = Field(default=0.0)
    total_mean_ms: float = Field(default=0.0)


class SystemReliabilityMetrics(BaseModel):
    """System-level error, fallback, and degradation rates."""
    model_config = ConfigDict(extra="forbid")

    total_requests: int = Field(default=0)
    failure_rate: float = Field(default=0.0)
    retry_rate: float = Field(default=0.0)
    fallback_rate: float = Field(default=0.0)
    degraded_mode_rate: float = Field(default=0.0)


class SystemOperationalMetrics(BaseModel):
    """Layer 3: Operational health, performance, and latency metrics."""
    model_config = ConfigDict(extra="forbid")

    search_latency: LatencyPercentiles = Field(default_factory=LatencyPercentiles)
    rag_latency: RAGLatencyDecomposition = Field(default_factory=RAGLatencyDecomposition)
    recommendation_latency: LatencyPercentiles = Field(default_factory=LatencyPercentiles)
    reliability: SystemReliabilityMetrics = Field(default_factory=SystemReliabilityMetrics)


# ==============================================================================
# IMMUTABLE SYSTEM EVALUATION ARTIFACT (Section 8)
# ==============================================================================

class SystemCatalogLimitations(BaseModel):
    """Honest catalog limitations and statistical significance disclosure."""
    model_config = ConfigDict(extra="forbid")

    active_product_count: int = Field(...)
    catalog_assessment: str = Field(...)
    statistical_validity: Literal["HIGH", "MODERATE", "LOW"] = Field(...)
    limitations_notice: str = Field(...)


class SystemEvaluationArtifact(BaseModel):
    """Top-level immutable evaluation artifact for Phase 09."""
    model_config = ConfigDict(extra="forbid")

    evaluation_version: str = Field(default="system_v1")
    run_id: str = Field(..., description="Unique timestamped run identifier.")
    timestamp: str = Field(..., description="ISO 8601 execution timestamp.")
    overall_status: EvaluationStatus = Field(..., description="PASSED, FAILED, or ERROR.")

    hard_correctness_gates: HardCorrectnessGateResult = Field(..., description="Non-negotiable correctness gates.")
    integration_checks: SystemIntegrationSummary = Field(..., description="Scenarios A through F cross-subsystem checks.")
    quality_metrics: SystemQualityMetrics = Field(..., description="Component quality metrics (reported independently).")
    operational_metrics: SystemOperationalMetrics = Field(..., description="Latency and reliability operational metrics.")

    catalog_limitations: SystemCatalogLimitations = Field(..., description="Catalog size and statistical disclosures.")
    system_configuration: dict[str, Any] = Field(default_factory=dict, description="Live system configuration.")
    errors: list[str] = Field(default_factory=list, description="Evaluator errors or execution exceptions.")
