"""Execution Target Adapters for Step 07.1 Retrieval Evaluation.

Implements Q70:
- Target-agnostic AdapterExecutionResult
- ServiceAdapter: Directly calls HybridSearchService in-process, capturing pure search latency
- ApiAdapter: Calls GET /api/v1/search via FastAPI TestClient, capturing API round-trip latency
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.main import app
from app.schemas.evaluation import BenchmarkCase, NormalizedSearchResult
from app.schemas.search import SearchResponse
from app.services.hybrid_search_service import HybridSearchService


class AdapterExecutionResult(BaseModel):
    """Normalized output from any evaluation target adapter."""
    model_config = ConfigDict(extra="forbid")

    results: list[NormalizedSearchResult] = Field(default_factory=list)
    returned_count: int = Field(default=0)
    latency_ms: float = Field(..., description="Measured latency in milliseconds.")
    k_expanded: bool = Field(default=False)
    candidate_ids: dict[str, list[int]] = Field(
        default_factory=dict,
        description="Candidate product IDs per retrieval branch (mysql, faiss, union)."
    )
    raw_response: Optional[dict[str, Any]] = Field(default=None)
    error: Optional[str] = Field(default=None)


class EvaluationTargetPort(ABC):
    """Port for benchmark execution targets."""

    @abstractmethod
    def execute(self, case: BenchmarkCase, db: Optional[Session] = None) -> AdapterExecutionResult:
        """Executes a benchmark query and returns a normalized result."""
        pass


class ServiceAdapter(EvaluationTargetPort):
    """Primary benchmark execution adapter invoking HybridSearchService in-process (Q70).
    
    Latency measured: service_search_latency_ms (pure search algorithm execution).
    """

    def __init__(self, search_service: Optional[HybridSearchService] = None):
        self.search_service = search_service or HybridSearchService()

    def execute(self, case: BenchmarkCase, db: Optional[Session] = None) -> AdapterExecutionResult:
        if db is None:
            return AdapterExecutionResult(
                latency_ms=0.0,
                error="Database session required for ServiceAdapter execution."
            )

        try:
            response: SearchResponse = self.search_service.search(
                db=db,
                raw_query=case.query_text,
                limit=case.limit,
                debug=True
            )

            # Map to NormalizedSearchResult
            normalized_results = []
            for rank_idx, item in enumerate(response.results, start=1):
                normalized_results.append(
                    NormalizedSearchResult(
                        product_id=item.product.id,
                        score=item.score,
                        rank=rank_idx,
                        match_reasons=item.match_reasons,
                        product=item.product
                    )
                )

            # Extract decomposed candidate IDs from debug diagnostics if available
            candidate_ids = {}
            if response.debug_diagnostics and "candidate_ids" in response.debug_diagnostics:
                candidate_ids = response.debug_diagnostics["candidate_ids"]

            return AdapterExecutionResult(
                results=normalized_results,
                returned_count=len(normalized_results),
                latency_ms=response.metadata.took_ms,  # service_search_latency_ms
                k_expanded=response.metadata.k_expanded,
                candidate_ids=candidate_ids,
                raw_response=response.model_dump(),
                error=None
            )
        except Exception as exc:
            return AdapterExecutionResult(
                latency_ms=0.0,
                error=f"ServiceAdapter execution error: {str(exc)}"
            )


class ApiAdapter(EvaluationTargetPort):
    """Secondary benchmark execution adapter invoking GET /api/v1/search (Q70).
    
    Used for Smoke tier & API contract verification.
    Latency measured: api_round_trip_latency_ms (includes HTTP/FastAPI serialization).
    """

    def __init__(self, test_client: Optional[TestClient] = None):
        self.client = test_client or TestClient(app)

    def execute(self, case: BenchmarkCase, db: Optional[Session] = None) -> AdapterExecutionResult:
        start_wall = time.perf_counter()
        try:
            params = {
                "q": case.query_text,
                "limit": case.limit or 20,
                "debug": "true"
            }
            resp = self.client.get("/api/v1/search", params=params)
            api_latency_ms = round((time.perf_counter() - start_wall) * 1000.0, 2)

            if resp.status_code != 200:
                return AdapterExecutionResult(
                    latency_ms=api_latency_ms,
                    error=f"HTTP {resp.status_code}: {resp.text}"
                )

            # Validate against Pydantic response schema
            payload = resp.json()
            search_resp = SearchResponse.model_validate(payload)

            normalized_results = []
            for rank_idx, item in enumerate(search_resp.results, start=1):
                normalized_results.append(
                    NormalizedSearchResult(
                        product_id=item.product.id,
                        score=item.score,
                        rank=rank_idx,
                        match_reasons=item.match_reasons,
                        product=item.product
                    )
                )

            candidate_ids = {}
            if search_resp.debug_diagnostics and "candidate_ids" in search_resp.debug_diagnostics:
                candidate_ids = search_resp.debug_diagnostics["candidate_ids"]

            return AdapterExecutionResult(
                results=normalized_results,
                returned_count=len(normalized_results),
                latency_ms=api_latency_ms,  # api_round_trip_latency_ms
                k_expanded=search_resp.metadata.k_expanded,
                candidate_ids=candidate_ids,
                raw_response=payload,
                error=None
            )
        except Exception as exc:
            api_latency_ms = round((time.perf_counter() - start_wall) * 1000.0, 2)
            return AdapterExecutionResult(
                latency_ms=api_latency_ms,
                error=f"ApiAdapter execution error: {str(exc)}"
            )
