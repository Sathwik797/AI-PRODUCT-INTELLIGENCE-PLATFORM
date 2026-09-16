"""System Evaluation Runner for Phase 09.

Implements Q94 & Q95:
- Coordinates Layer 1 (Component Quality), Layer 2 (Integration Quality), Layer 3 (Operational Health).
- Evaluates non-negotiable Hard Correctness Gates.
- Enforces strict status semantics:
  * PASSED: all hard gates pass and evaluation succeeds.
  * FAILED: evaluation completes, but one or more hard gates fail.
  * ERROR: evaluation infrastructure itself fails to execute.
- Persists immutable versioned artifact to evaluation/results/system_eval_*.json and updates latest_system.json.
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal
from app.evaluation.system.component import ComponentQualityEvaluator
from app.evaluation.system.gates import HardCorrectnessGateEvaluator
from app.evaluation.system.integration import SystemIntegrationValidator
from app.evaluation.system.operational import OperationalMetricsCollector
from app.models.product import Product
from app.schemas.rag import RAGConfig
from app.schemas.recommendation import RecommendationConfig
from app.schemas.search import HybridSearchConfig
from app.schemas.system_evaluation import (
    EvaluationStatus,
    HardCorrectnessGateResult,
    SystemCatalogLimitations,
    SystemEvaluationArtifact,
    SystemIntegrationSummary,
    SystemOperationalMetrics,
    SystemQualityMetrics,
)

logger = logging.getLogger(__name__)

RESULTS_DIR = Path("evaluation/results")


class SystemEvaluationRunner:
    """Orchestrates comprehensive, layered system-wide evaluation across all platform subsystems."""

    def __init__(
        self,
        results_dir: str | Path = RESULTS_DIR,
        integration_validator: Optional[SystemIntegrationValidator] = None,
        component_evaluator: Optional[ComponentQualityEvaluator] = None,
        operational_collector: Optional[OperationalMetricsCollector] = None,
        gate_evaluator: Optional[HardCorrectnessGateEvaluator] = None
    ):
        self.results_dir = Path(results_dir)
        self.integration_validator = integration_validator or SystemIntegrationValidator()
        self.component_evaluator = component_evaluator or ComponentQualityEvaluator()
        self.operational_collector = operational_collector or OperationalMetricsCollector()
        self.gate_evaluator = gate_evaluator or HardCorrectnessGateEvaluator()

    def run(
        self,
        db: Optional[Session] = None,
        save_artifact: bool = True
    ) -> SystemEvaluationArtifact:
        """Executes full system-wide layered evaluation.

        Returns:
            Immutable SystemEvaluationArtifact with complete provenance and measurements.
        """
        owns_session = False
        if db is None:
            db = SessionLocal()
            owns_session = True

        run_id = f"system_eval_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        errors: list[str] = []

        try:
            # 1. Catalog Limitations & Statistical Significance Assessment
            active_count = db.query(Product).filter(Product.status == "ACTIVE").count()
            if active_count >= 500:
                stat_validity = "HIGH"
                cat_notice = "Catalog size is statistically representative for production evaluation."
            elif active_count >= 20:
                stat_validity = "MODERATE"
                cat_notice = "Catalog size is sufficient for integration and candidate verification."
            else:
                stat_validity = "LOW"
                cat_notice = (
                    f"Catalog contains {active_count} active product(s). Metric averages reflect catalog size, "
                    "not platform architecture defects. Hard correctness invariants remain strictly enforced."
                )

            limitations = SystemCatalogLimitations(
                active_product_count=active_count,
                catalog_assessment=f"{active_count} active catalog products",
                statistical_validity=stat_validity,
                limitations_notice=cat_notice
            )

            # 2. Live System Configuration Introspection
            search_cfg = HybridSearchConfig()
            rag_cfg = RAGConfig()
            rec_cfg = RecommendationConfig()
            system_config = {
                "app_name": settings.app_name,
                "app_version": settings.app_version,
                "search": search_cfg.model_dump(),
                "rag": rag_cfg.model_dump(),
                "recommendation": rec_cfg.model_dump()
            }

            # 3. Layer 2: System Integration Scenarios (Scenarios A through F)
            integration_summary: SystemIntegrationSummary = self.integration_validator.run_all_scenarios(db)

            # 4. Layer 1: Component Quality Metrics
            quality_metrics: SystemQualityMetrics = self.component_evaluator.evaluate_all(db)

            # 5. Layer 3: Operational Health & Latency Metrics
            operational_metrics: SystemOperationalMetrics = self.operational_collector.collect(db)

            # 6. Aggregate Hard Correctness Violations
            # Tally violations from integration checks and component quality metrics
            invalid_citations = 0
            hard_filter_violations = quality_metrics.search.hard_filter_violations if hasattr(quality_metrics.search, "hard_filter_violations") else 0
            inactive_leaks = 0
            unaccepted_leaks = 0
            self_returns = 0
            canonical_inconsistencies = 0

            for s_key, s_detail in integration_summary.scenarios.items():
                if not s_detail.passed:
                    for v in s_detail.violations:
                        v_lower = v.lower()
                        if "citation" in v_lower:
                            invalid_citations += 1
                        elif "filter" in v_lower or "price was found inside" in v_lower:
                            hard_filter_violations += 1
                        elif "inactive" in v_lower or "archived" in v_lower:
                            inactive_leaks += 1
                        elif "unaccepted" in v_lower or "rejected" in v_lower:
                            unaccepted_leaks += 1
                        elif "self" in v_lower or "itself" in v_lower:
                            self_returns += 1
                        else:
                            canonical_inconsistencies += 1

            if quality_metrics.recommendations.self_return_rate > 0.0:
                self_returns += 1

            hard_gates: HardCorrectnessGateResult = self.gate_evaluator.evaluate(
                invalid_citations=invalid_citations,
                hard_filter_violations=hard_filter_violations,
                inactive_product_leaks=inactive_leaks,
                unaccepted_metadata_leaks=unaccepted_leaks,
                recommendation_self_returns=self_returns,
                canonical_data_inconsistencies=canonical_inconsistencies,
                total_checks=6 + sum(s.checks_performed for s in integration_summary.scenarios.values())
            )

            # 7. Status Semantics: PASSED if all hard gates pass, FAILED if any violation exists
            overall_status: EvaluationStatus = "PASSED" if hard_gates.passed else "FAILED"

            artifact = SystemEvaluationArtifact(
                evaluation_version="system_v1",
                run_id=run_id,
                timestamp=now_iso,
                overall_status=overall_status,
                hard_correctness_gates=hard_gates,
                integration_checks=integration_summary,
                quality_metrics=quality_metrics,
                operational_metrics=operational_metrics,
                catalog_limitations=limitations,
                system_configuration=system_config,
                errors=errors
            )

        except Exception as e:
            logger.exception(f"Catastrophic error during system evaluation: {e}")
            overall_status = "ERROR"
            errors.append(str(e))
            # Fallback error artifact
            empty_gates = HardCorrectnessGateResult(
                passed=False,
                total_checks=0,
                total_violations=1,
                violations={
                    "invalid_citations": 0,
                    "hard_filter_violations": 0,
                    "inactive_product_leaks": 0,
                    "unaccepted_metadata_leaks": 0,
                    "recommendation_self_returns": 0,
                    "canonical_data_inconsistencies": 1
                },
                failure_reasons=[f"Evaluator error: {e}"]
            )
            artifact = SystemEvaluationArtifact(
                evaluation_version="system_v1",
                run_id=run_id,
                timestamp=now_iso,
                overall_status=overall_status,
                hard_correctness_gates=empty_gates,
                integration_checks=SystemIntegrationSummary(all_passed=False, scenarios={}),
                quality_metrics=SystemQualityMetrics(),
                operational_metrics=SystemOperationalMetrics(),
                catalog_limitations=SystemCatalogLimitations(
                    active_product_count=0,
                    catalog_assessment="Error",
                    statistical_validity="LOW",
                    limitations_notice="Evaluation error"
                ),
                system_configuration={},
                errors=errors
            )

        finally:
            if owns_session:
                db.close()

        # 8. Persist Artifact & Update Mutable Latest Pointer
        if save_artifact:
            self.results_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = self.results_dir / f"{run_id}.json"
            with open(artifact_path, "w", encoding="utf-8") as f:
                f.write(artifact.model_dump_json(indent=2))
            logger.info(f"Saved immutable system evaluation artifact to {artifact_path}")

            latest_path = self.results_dir / "latest_system.json"
            with open(latest_path, "w", encoding="utf-8") as f:
                f.write(artifact.model_dump_json(indent=2))
            logger.info(f"Updated latest system evaluation pointer at {latest_path}")

        return artifact
