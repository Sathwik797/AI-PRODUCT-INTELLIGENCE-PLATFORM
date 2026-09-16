"""Benchmark Runner and Evaluation Orchestration Engine for Step 07.1.

Implements Q65, Q68, Q69, Q70:
- Sequential execution of BenchmarkSuite against ServiceAdapter or ApiAdapter
- Live system provenance introspection (zero hardcoding)
- Honest catalog limitations disclosure (Repair 3)
- Metric aggregation: Recall decomposition (MySQL/FAISS/Union), NDCG@10/20, MRR, 0% violation gate
- Latency separation: service_search_latency_ms vs api_round_trip_latency_ms (Repair 4)
- Immutable historical artifact (<run_id>.json) + mutable convenience pointer (latest.json) (Repair 6)
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.ai.embedding_text_builder import BUILDER_VERSION
from app.db.database import SessionLocal
from app.evaluation.adapters import (
    AdapterExecutionResult,
    ApiAdapter,
    EvaluationTargetPort,
    ServiceAdapter,
)
from app.evaluation.metrics import (
    IndependentHardConstraintValidator,
    calculate_hit_rate_at_k,
    calculate_mrr,
    calculate_ndcg_at_k,
    calculate_percentiles,
    calculate_recall_at_k,
)
from app.models.product import Product
from app.schemas.evaluation import (
    BenchmarkCase,
    BenchmarkSuite,
    CatalogLimitations,
    EvaluationRun,
    MetricSummary,
    QueryEvaluationResult,
    QueryTypeBreakdown,
)
from app.services.embedding_service import EmbeddingService
from app.services.hybrid_search_service import HybridSearchService

logger = logging.getLogger(__name__)
RESULTS_DIR = Path("evaluation/results")


class BenchmarkRunner:
    """Executes a benchmark suite and produces immutable evaluation run artifacts."""

    def __init__(
        self,
        search_service: Optional[HybridSearchService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        results_dir: Optional[Path] = None
    ):
        self.search_service = search_service or HybridSearchService()
        self.embedding_service = embedding_service or EmbeddingService()
        self.results_dir = results_dir or RESULTS_DIR
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def introspect_live_provenance(self) -> dict[str, Any]:
        """Introspects live system configuration directly from active service instances (Repair 1).
        
        Zero hardcoded constants.
        """
        provider = self.search_service.semantic_retriever.provider
        config = self.search_service.config

        return {
            "embedding_model": getattr(provider, "model_name", "unknown"),
            "embedding_dimension": getattr(provider, "dimension", 768),
            "text_builder_version": BUILDER_VERSION,
            "mysql_candidate_k": config.mysql_candidate_k,
            "faiss_candidate_k": config.faiss_candidate_k,
            "max_candidate_k": config.max_candidate_k,
            "default_limit": config.default_limit,
            "enable_expansion": config.enable_expansion,
            "semantic_weight": config.semantic_weight,
            "structured_weight": config.structured_weight,
        }

    def assess_catalog_limitations(self, db: Session) -> CatalogLimitations:
        """Determines active catalog size and generates honest statistical significance notice (Repair 3)."""
        active_count = db.query(Product).filter(Product.status == "ACTIVE").count()

        if active_count <= 5:
            significance = "LOW"
            notice = (
                f"Catalog contains {active_count} active product(s); "
                "ranking and retrieval metrics have limited statistical significance."
            )
        elif active_count <= 50:
            significance = "MODERATE"
            notice = f"Catalog contains {active_count} active products; moderate statistical confidence."
        else:
            significance = "HIGH"
            notice = f"Catalog contains {active_count} active products; high statistical confidence."

        return CatalogLimitations(
            active_product_count=active_count,
            statistical_significance=significance,
            notice=notice
        )

    def run(
        self,
        suite: BenchmarkSuite,
        target: str = "service",
        save_artifact: bool = True,
        db: Optional[Session] = None
    ) -> EvaluationRun:
        """Executes full benchmark suite against the chosen target adapter."""
        owns_session = False
        if db is None:
            db = SessionLocal()
            owns_session = True

        try:
            # 1. Instantiate appropriate Target Adapter (Q70)
            adapter: EvaluationTargetPort
            if target == "service":
                adapter = ServiceAdapter(search_service=self.search_service)
            elif target == "api":
                adapter = ApiAdapter()
            else:
                raise ValueError(f"Unsupported target '{target}'. Must be 'service' or 'api'.")

            provenance = self.introspect_live_provenance()
            limitations = self.assess_catalog_limitations(db)

            query_results: list[QueryEvaluationResult] = []
            latencies: list[float] = []
            total_returned_items = 0
            total_violations = 0
            expansion_count = 0
            failed_queries = 0

            # 2. Sequential Query Evaluation
            for case in suite.cases:
                adapter_res: AdapterExecutionResult = adapter.execute(case, db=db)

                if adapter_res.error:
                    failed_queries += 1
                    query_results.append(
                        QueryEvaluationResult(
                            benchmark_id=case.benchmark_id,
                            query_text=case.query_text,
                            track=case.track,
                            query_type=case.query_type,
                            returned_count=0,
                            recall_at_k={},
                            hit_rate_at_10=0.0,
                            ndcg_at_10=None,
                            ndcg_at_20=None,
                            mrr=None,
                            hard_filter_violations=0,
                            zero_result_correct=None,
                            k_expanded=False,
                            latency_ms=adapter_res.latency_ms,
                            error=adapter_res.error
                        )
                    )
                    continue

                latencies.append(adapter_res.latency_ms)
                if adapter_res.k_expanded:
                    expansion_count += 1

                retrieved_ids = [r.product_id for r in adapter_res.results]
                total_returned_items += len(retrieved_ids)

                # Decomposed Recall (MySQL / FAISS / Union)
                recall_dict: dict[str, float] = {}
                if adapter_res.candidate_ids:
                    r_sql = calculate_recall_at_k(adapter_res.candidate_ids.get("mysql", []), case.ground_truth, k=100)
                    r_faiss = calculate_recall_at_k(adapter_res.candidate_ids.get("faiss", []), case.ground_truth, k=100)
                    r_union = calculate_recall_at_k(adapter_res.candidate_ids.get("union", []), case.ground_truth, k=100)

                    if r_sql is not None: recall_dict["mysql"] = round(r_sql, 4)
                    if r_faiss is not None: recall_dict["faiss"] = round(r_faiss, 4)
                    if r_union is not None: recall_dict["union"] = round(r_union, 4)
                else:
                    # Fallback to returned IDs if candidate debug unavailable
                    r_ret = calculate_recall_at_k(retrieved_ids, case.ground_truth, k=len(retrieved_ids))
                    if r_ret is not None:
                        recall_dict["returned"] = round(r_ret, 4)

                # Ranking metrics
                ndcg_10 = calculate_ndcg_at_k(retrieved_ids, case.ground_truth, k=10)
                ndcg_20 = calculate_ndcg_at_k(retrieved_ids, case.ground_truth, k=20)
                mrr_val = calculate_mrr(retrieved_ids, case.ground_truth)
                hit_rate = calculate_hit_rate_at_k(retrieved_ids, case.ground_truth, k=10) or 0.0

                # Independent Hard Constraint Validation (Repair 2: Ground truth remains strictly immutable)
                query_violations = 0
                for norm_item in adapter_res.results:
                    if norm_item.product:
                        meta = self.embedding_service.get_accepted_ai_metadata(db, norm_item.product_id)
                        violations = IndependentHardConstraintValidator.validate_product(
                            product=norm_item.product,
                            expected_constraints=case.expected_constraints,
                            accepted_metadata=meta
                        )
                        if violations:
                            query_violations += len(violations)

                total_violations += query_violations

                # Zero-result query evaluation
                zero_correct = None
                if case.is_zero_result_expected:
                    zero_correct = (len(retrieved_ids) == 0)

                query_results.append(
                    QueryEvaluationResult(
                        benchmark_id=case.benchmark_id,
                        query_text=case.query_text,
                        track=case.track,
                        query_type=case.query_type,
                        returned_count=len(retrieved_ids),
                        recall_at_k=recall_dict,
                        hit_rate_at_10=round(hit_rate, 4),
                        ndcg_at_10=round(ndcg_10, 4) if ndcg_10 is not None else None,
                        ndcg_at_20=round(ndcg_20, 4) if ndcg_20 is not None else None,
                        mrr=round(mrr_val, 4) if mrr_val is not None else None,
                        hard_filter_violations=query_violations,
                        zero_result_correct=zero_correct,
                        k_expanded=adapter_res.k_expanded,
                        latency_ms=adapter_res.latency_ms,
                        error=None
                    )
                )

            # 3. Macro-Averaging Summary Metrics
            eligible_ndcg_10 = [r.ndcg_at_10 for r in query_results if r.ndcg_at_10 is not None]
            eligible_ndcg_20 = [r.ndcg_at_20 for r in query_results if r.ndcg_at_20 is not None]
            eligible_mrr = [r.mrr for r in query_results if r.mrr is not None]
            eligible_rec_sql = [r.recall_at_k["mysql"] for r in query_results if "mysql" in r.recall_at_k]
            eligible_rec_faiss = [r.recall_at_k["faiss"] for r in query_results if "faiss" in r.recall_at_k]
            eligible_rec_union = [r.recall_at_k["union"] for r in query_results if "union" in r.recall_at_k]
            eligible_hit_rates = [r.hit_rate_at_10 for r in query_results if not r.error]

            mean_ndcg_10 = round(sum(eligible_ndcg_10) / len(eligible_ndcg_10), 4) if eligible_ndcg_10 else 0.0
            mean_ndcg_20 = round(sum(eligible_ndcg_20) / len(eligible_ndcg_20), 4) if eligible_ndcg_20 else 0.0
            mean_mrr = round(sum(eligible_mrr) / len(eligible_mrr), 4) if eligible_mrr else 0.0
            mean_sql_recall = round(sum(eligible_rec_sql) / len(eligible_rec_sql), 4) if eligible_rec_sql else 0.0
            mean_faiss_recall = round(sum(eligible_rec_faiss) / len(eligible_rec_faiss), 4) if eligible_rec_faiss else 0.0
            mean_union_recall = round(sum(eligible_rec_union) / len(eligible_rec_union), 4) if eligible_rec_union else 0.0
            mean_hit_rate = round(sum(eligible_hit_rates) / len(eligible_hit_rates), 4) if eligible_hit_rates else 0.0

            violation_rate = 0.0
            if total_returned_items > 0:
                violation_rate = round(total_violations / total_returned_items, 4)

            p50, p95, p99 = calculate_percentiles(latencies)
            expansion_rate = round(expansion_count / max(1, len(suite.cases)), 4)

            summary = MetricSummary(
                total_queries=len(suite.cases),
                successful_queries=len(suite.cases) - failed_queries,
                failed_queries=failed_queries,
                ndcg_at_10=mean_ndcg_10,
                ndcg_at_20=mean_ndcg_20,
                mrr=mean_mrr,
                candidate_recall_mysql=mean_sql_recall,
                candidate_recall_faiss=mean_faiss_recall,
                candidate_recall_union=mean_union_recall,
                hit_rate_at_10=mean_hit_rate,
                hard_filter_violation_rate=violation_rate,
                total_hard_filter_violations=total_violations,
                k_expansion_rate=expansion_rate,
                latency_p50_ms=p50,
                latency_p95_ms=p95,
                latency_p99_ms=p99
            )

            # 4. Partition by Query Archetype (Q68)
            archetypes = ["exact_attribute", "compound_constraints", "semantic_intent", "edge_cases", "zero_result"]
            breakdown: dict[str, QueryTypeBreakdown] = {}

            for arch in archetypes:
                arch_items = [r for r in query_results if r.query_type == arch]
                if not arch_items:
                    continue

                arch_ndcg_10 = [r.ndcg_at_10 for r in arch_items if r.ndcg_at_10 is not None]
                arch_ndcg_20 = [r.ndcg_at_20 for r in arch_items if r.ndcg_at_20 is not None]
                arch_mrr = [r.mrr for r in arch_items if r.mrr is not None]
                arch_rec = [r.recall_at_k["union"] for r in arch_items if "union" in r.recall_at_k]
                arch_violations = sum(r.hard_filter_violations for r in arch_items)

                zero_accuracy = None
                if arch == "zero_result":
                    zero_correct_list = [r.zero_result_correct for r in arch_items if r.zero_result_correct is not None]
                    if zero_correct_list:
                        zero_accuracy = round(sum(1 for c in zero_correct_list if c) / len(zero_correct_list), 4)

                breakdown[arch] = QueryTypeBreakdown(
                    query_count=len(arch_items),
                    mean_ndcg_at_10=round(sum(arch_ndcg_10) / len(arch_ndcg_10), 4) if arch_ndcg_10 else None,
                    mean_ndcg_at_20=round(sum(arch_ndcg_20) / len(arch_ndcg_20), 4) if arch_ndcg_20 else None,
                    mean_mrr=round(sum(arch_mrr) / len(arch_mrr), 4) if arch_mrr else None,
                    mean_union_recall=round(sum(arch_rec) / len(arch_rec), 4) if arch_rec else None,
                    hard_filter_violations=arch_violations,
                    zero_result_accuracy=zero_accuracy
                )

            # 5. Assemble Final Evaluation Run Artifact
            now_iso = datetime.now(timezone.utc).isoformat()
            run_id = f"eval_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{suite.tier}_{target}_{uuid.uuid4().hex[:6]}"
            correctness_gate_passed = (total_violations == 0 and failed_queries == 0)

            run_artifact = EvaluationRun(
                run_id=run_id,
                timestamp=now_iso,
                benchmark_name=suite.name,
                benchmark_tier=suite.tier,
                target=target,
                system_configuration=provenance,
                catalog_limitations=limitations,
                correctness_gate_passed=correctness_gate_passed,
                summary_metrics=summary,
                query_type_breakdown=breakdown,
                query_results=query_results
            )

            # 6. Immutable Artifact Persistence (Repair 6)
            if save_artifact:
                artifact_file = self.results_dir / f"{run_id}.json"
                with open(artifact_file, "w", encoding="utf-8") as f:
                    f.write(run_artifact.model_dump_json(indent=2))
                logger.info(f"Saved immutable evaluation artifact to {artifact_file}")

                # Update mutable convenience pointer
                latest_file = self.results_dir / "latest.json"
                with open(latest_file, "w", encoding="utf-8") as f:
                    f.write(run_artifact.model_dump_json(indent=2))
                logger.info(f"Updated latest evaluation pointer at {latest_file}")

            return run_artifact

        finally:
            if owns_session:
                db.close()
