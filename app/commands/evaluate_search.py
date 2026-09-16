"""Evaluation CLI Command for Step 07.1 Retrieval Evaluation Subsystem.

Implements Q65–Q70:
    python -m app.commands.evaluate_search --tier smoke --target service
    python -m app.commands.evaluate_search --tier smoke --target api
    python -m app.commands.evaluate_search --tier standard
    python -m app.commands.evaluate_search --tier extended
"""

import argparse
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from app.db.database import SessionLocal
from app.evaluation.dataset import (
    BENCHMARK_DIR,
    build_default_smoke_suite,
    load_benchmark_suite,
    save_benchmark_suite,
)
from app.evaluation.runner import BenchmarkRunner
from app.schemas.evaluation import BenchmarkSuite

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("evaluate_search")


def get_suite_for_tier(tier: str, db) -> BenchmarkSuite:
    """Retrieves or creates benchmark suite for requested tier."""
    suite_file = BENCHMARK_DIR / f"{tier}_v1.json"

    if suite_file.exists():
        return load_benchmark_suite(suite_file)

    if tier == "smoke":
        suite = build_default_smoke_suite(db=db)
        save_benchmark_suite(suite, suite_file)
        return suite
    elif tier == "standard":
        # For standard tier, if no file exists yet, generate smoke suite as baseline
        suite = build_default_smoke_suite(db=db)
        suite.name = "standard"
        suite.tier = "standard"
        save_benchmark_suite(suite, suite_file)
        return suite
    else:
        suite = build_default_smoke_suite(db=db)
        suite.name = tier
        suite.tier = tier
        save_benchmark_suite(suite, suite_file)
        return suite


def print_run_report(run) -> None:
    """Renders human-readable summary report to console."""
    m = run.summary_metrics
    c = run.catalog_limitations

    print("\n" + "=" * 78)
    print(f"SEARCH EVALUATION REPORT — RUN: {run.run_id}")
    print(f"Benchmark: {run.benchmark_name.upper()} (Tier: {run.benchmark_tier.upper()}, Target: {run.target.upper()})")
    print(f"Timestamp: {run.timestamp}")
    print("=" * 78)

    print("\n--- SYSTEM PROVENANCE (LIVE INTROSPECTION) ---")
    for k, v in run.system_configuration.items():
        print(f"  {k:25}: {v}")

    print("\n--- CATALOG LIMITATIONS NOTICE ---")
    print(f"  Active Product Count     : {c.active_product_count}")
    print(f"  Statistical Significance : {c.statistical_significance}")
    print(f"  Notice                   : {c.notice}")

    print("\n--- RETRIEVAL & RANKING METRICS ---")
    print(f"  Total Queries Evaluated  : {m.total_queries} ({m.successful_queries} succeeded, {m.failed_queries} failed)")
    print(f"  NDCG@10                  : {m.ndcg_at_10:.4f}")
    print(f"  NDCG@20                  : {m.ndcg_at_20:.4f}")
    print(f"  MRR                      : {m.mrr:.4f}")
    print(f"  HitRate@10               : {m.hit_rate_at_10:.4f}")
    print(f"  Candidate Recall (MySQL) : {m.candidate_recall_mysql:.4f}")
    print(f"  Candidate Recall (FAISS) : {m.candidate_recall_faiss:.4f}")
    print(f"  Candidate Recall (Union) : {m.candidate_recall_union:.4f}")

    print("\n--- CORRECTNESS GATE (ZERO TOLERANCE) ---")
    print(f"  Hard-Filter Violations   : {m.total_hard_filter_violations}")
    print(f"  Violation Rate           : {m.hard_filter_violation_rate * 100:.2f}% (Threshold: 0.00%)")
    gate_status = "PASSED [OK]" if run.correctness_gate_passed else "FAILED [VIOLATION DETECTED]"
    print(f"  Correctness Gate Status  : {gate_status}")

    print("\n--- PERFORMANCE & OPERATIONAL SLA ---")
    lat_label = "Service Search Latency" if run.target == "service" else "API Round-Trip Latency"
    print(f"  {lat_label} P50   : {m.latency_p50_ms:.2f} ms")
    print(f"  {lat_label} P95   : {m.latency_p95_ms:.2f} ms")
    print(f"  {lat_label} P99   : {m.latency_p99_ms:.2f} ms")
    print(f"  K-Expansion Rate         : {m.k_expansion_rate * 100:.2f}%")

    print("\n--- QUERY-TYPE BREAKDOWN (5 ARCHETYPES) ---")
    print(f"  {'Archetype':<22} | {'Count':<5} | {'NDCG@10':<7} | {'MRR':<7} | {'Union Rec':<9} | {'Violations':<10} | {'Zero Acc':<8}")
    print("  " + "-" * 76)
    for arch, stats in run.query_type_breakdown.items():
        n10 = f"{stats.mean_ndcg_at_10:.4f}" if stats.mean_ndcg_at_10 is not None else "N/A"
        mrr = f"{stats.mean_mrr:.4f}" if stats.mean_mrr is not None else "N/A"
        urec = f"{stats.mean_union_recall:.4f}" if stats.mean_union_recall is not None else "N/A"
        zacc = f"{stats.zero_result_accuracy:.4f}" if stats.zero_result_accuracy is not None else "N/A"
        print(f"  {arch:<22} | {stats.query_count:<5} | {n10:<7} | {mrr:<7} | {urec:<9} | {stats.hard_filter_violations:<10} | {zacc:<8}")
    print("=" * 78 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Evaluate Hybrid Search retrieval and ranking quality.")
    parser.add_argument(
        "--tier",
        type=str,
        default="smoke",
        choices=["smoke", "standard", "extended"],
        help="Benchmark tier to execute."
    )
    parser.add_argument(
        "--target",
        type=str,
        default="service",
        choices=["service", "api"],
        help="Target adapter to execute against (service=HybridSearchService, api=/api/v1/search)."
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not persist results to evaluation/results/."
    )

    args = parser.parse_args()

    db = SessionLocal()
    try:
        suite = get_suite_for_tier(args.tier, db=db)
        runner = BenchmarkRunner()
        run = runner.run(
            suite=suite,
            target=args.target,
            save_artifact=not args.no_save,
            db=db
        )

        print_run_report(run)

        # Non-zero exit code if correctness gate failed or query execution errors
        if not run.correctness_gate_passed:
            logger.error("Evaluation run FAILED the correctness gate (violations detected or query errors).")
            sys.exit(1)
        else:
            logger.info("Evaluation run PASSED the correctness gate.")
            sys.exit(0)
    finally:
        db.close()


if __name__ == "__main__":
    main()
