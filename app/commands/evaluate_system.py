"""System-wide Evaluation CLI Command.

Usage:
    python -m app.commands.evaluate_system
    python -m app.commands.evaluate_system --no-save
    python -m app.commands.evaluate_system --results-dir custom_dir
"""

import argparse
import logging
import sys
from dotenv import load_dotenv

load_dotenv()

from app.db.database import SessionLocal
from app.evaluation.system.runner import SystemEvaluationRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("evaluate_system")


def main():
    parser = argparse.ArgumentParser(description="Phase 09 System-wide Evaluation CLI")
    parser.add_argument("--no-save", action="store_true", help="Do not persist evaluation artifact to disk")
    parser.add_argument("--results-dir", type=str, default="evaluation/results", help="Directory for evaluation artifacts")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        runner = SystemEvaluationRunner(results_dir=args.results_dir)
        print("=" * 70)
        print("EXECUTING PHASE 09 — SYSTEM-WIDE EVALUATION")
        print("=" * 70)

        artifact = runner.run(db=db, save_artifact=not args.no_save)

        print("\n" + "=" * 70)
        print("EVALUATION RUN SUMMARY")
        print("=" * 70)
        print(f"Run ID:            {artifact.run_id}")
        print(f"Timestamp:         {artifact.timestamp}")
        print(f"Overall Status:    {artifact.overall_status}")
        print("-" * 70)
        print("HARD CORRECTNESS GATES:")
        print(f"  Passed:          {artifact.hard_correctness_gates.passed}")
        print(f"  Total Checks:    {artifact.hard_correctness_gates.total_checks}")
        print(f"  Total Violations:{artifact.hard_correctness_gates.total_violations}")
        for k, v in artifact.hard_correctness_gates.violations.model_dump().items():
            status_icon = "PASS" if v == 0 else "FAIL"
            print(f"    - {k:<32}: {v} [{status_icon}]")

        print("-" * 70)
        print("INTEGRATION SCENARIOS:")
        for s_key, s_data in artifact.integration_checks.scenarios.items():
            status_icon = "PASS" if s_data.passed else "FAIL"
            print(f"  [{status_icon}] {s_data.scenario_name} (Checks: {s_data.checks_performed}, Violations: {len(s_data.violations)})")

        print("-" * 70)
        print("COMPONENT QUALITY METRICS (Independent):")
        print(f"  Search Recall@10:       {artifact.quality_metrics.search.recall_at_10}")
        print(f"  Search NDCG@10:         {artifact.quality_metrics.search.ndcg_at_10}")
        print(f"  RAG Citation Validity:  {artifact.quality_metrics.rag.citation_validity_rate}")
        print(f"  RAG Schema Validity:    {artifact.quality_metrics.rag.schema_validity_rate}")
        print(f"  Rec Candidate Coverage: {artifact.quality_metrics.recommendations.eligible_candidate_coverage}")
        print(f"  Embedding Hash Match:   {artifact.quality_metrics.embeddings.hash_consistency_rate}")

        print("-" * 70)
        print("OPERATIONAL HEALTH & LATENCY:")
        print(f"  Search P50 Latency:     {artifact.operational_metrics.search_latency.p50_ms} ms")
        print(f"  Search P95 Latency:     {artifact.operational_metrics.search_latency.p95_ms} ms")
        print(f"  Recs P50 Latency:       {artifact.operational_metrics.recommendation_latency.p50_ms} ms")
        print(f"  RAG Retrieval Mean:     {artifact.operational_metrics.rag_latency.retrieval_mean_ms} ms")
        print(f"  System Degraded Rate:   {artifact.operational_metrics.reliability.degraded_mode_rate}")
        print("=" * 70)

        if artifact.overall_status != "PASSED":
            sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    main()
