"""Phase 09 System-wide Evaluation Focused Verification Suite.

Verifies:
1. Scenario A: Accepted AI metadata propagates into embedding, search availability, and RAG knowledge.
2. Scenario B: Rejected/pending AI metadata is isolated from embeddings, search, and RAG.
3. Scenario C: Volatile price updates do NOT alter embedding document/hash, but update Search & RAG.
4. Scenario D: Inactive products (status != 'ACTIVE') are excluded from search, RAG, and recs.
5. Scenario E: Search -> RAG consistency (exact product candidate and live state preservation).
6. Scenario F: Recommendation catalog consistency (active products only, never self-recommends).
7. Invalid citation triggers hard-gate failure (overall status = FAILED).
8. Hard-filter violation triggers hard-gate failure (overall status = FAILED).
9. Unaccepted metadata leak triggers hard-gate failure (overall status = FAILED).
10. Recommendation self-return triggers hard-gate failure (overall status = FAILED).
11. Component quality metrics remain strictly independent (zero artificial aggregate score).
12. Operational latency percentiles (P50/P95/P99) and reliability metrics collected.
13. Strict status semantics: PASSED, FAILED, and ERROR states verified.
14. Immutable versioned artifact saved with latest_system.json pointer updated.
"""

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Optional
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.evaluation.system.component import ComponentQualityEvaluator
from app.evaluation.system.gates import HardCorrectnessGateEvaluator
from app.evaluation.system.integration import SystemIntegrationValidator
from app.evaluation.system.operational import OperationalMetricsCollector, compute_percentiles
from app.evaluation.system.runner import SystemEvaluationRunner
from app.models.product import Product
from app.schemas.system_evaluation import (
    HardCorrectnessGateResult,
    HardGateViolationCounts,
    ScenarioCheckDetail,
    SystemCatalogLimitations,
    SystemEvaluationArtifact,
    SystemIntegrationSummary,
    SystemOperationalMetrics,
    SystemQualityMetrics,
)


def run_all_checks():
    passed = 0
    failed = 0
    total = 14

    print("=" * 70)
    print("PHASE 09 — SYSTEM-WIDE EVALUATION VERIFICATION SUITE")
    print("=" * 70)

    # --------------------------------------------------------------------------
    # Check 1: Scenario A — Accepted metadata propagation
    # --------------------------------------------------------------------------
    try:
        mock_emb_svc = MagicMock()
        mock_emb_svc.get_accepted_ai_metadata.return_value = {
            "attributes": {"material": {"type": "text", "value": "Leather"}}
        }
        mock_emb_svc.build_embedding_document.return_value = ("Title: Shoe Brand: Nike Attributes: material: Leather", "hash123")

        mock_rag_ret = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.product_id = 2
        mock_attr = MagicMock()
        mock_attr.attribute = "material"
        mock_ctx.verified_attributes = [mock_attr]
        mock_bundle = MagicMock()
        mock_bundle.products = [mock_ctx]
        mock_rag_ret.retrieve_and_hydrate.return_value = (mock_bundle, MagicMock())

        validator = SystemIntegrationValidator(
            embedding_service=mock_emb_svc,
            rag_retrieval_service=mock_rag_ret
        )

        mock_db = MagicMock()
        mock_prod = MagicMock()
        mock_prod.id = 2
        mock_prod.title = "Air Force"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_prod

        detail = validator.verify_scenario_a_accepted_propagation(mock_db, product_id=2)
        assert detail.passed is True, f"Expected Scenario A to pass, violations: {detail.violations}"
        assert detail.checks_performed > 0
        print("[PASS] Check 1: Scenario A verified accepted AI metadata propagation")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 1: Scenario A propagation: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 2: Scenario B — Rejected metadata isolation
    # --------------------------------------------------------------------------
    try:
        validator = SystemIntegrationValidator()
        mock_db = MagicMock()
        mock_prod = MagicMock()
        mock_prod.id = 2
        mock_prod.title = "Shoe"
        mock_prod.brand = "Nike"
        mock_prod.description = "Nice"
        mock_prod.category = None
        mock_db.query.return_value.filter.return_value.first.return_value = mock_prod

        detail = validator.verify_scenario_b_rejected_isolation(mock_db, product_id=2)
        assert detail.passed is True, f"Expected Scenario B to pass, violations: {detail.violations}"
        print("[PASS] Check 2: Scenario B verified rejected/unaccepted metadata isolation")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 2: Scenario B isolation: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 3: Scenario C — Volatile field isolation
    # --------------------------------------------------------------------------
    try:
        mock_emb_svc = MagicMock()
        # Price is excluded from embedding document text
        mock_emb_svc.build_embedding_document.return_value = ("Title: Shoe Brand: Nike Attributes: material: Leather", "hash_stable")

        mock_rag_ret = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.live_catalog_state = {"price": 7499.0}
        mock_rag_ret._hydrate_single_product.return_value = mock_ctx

        validator = SystemIntegrationValidator(
            embedding_service=mock_emb_svc,
            rag_retrieval_service=mock_rag_ret
        )

        mock_db = MagicMock()
        mock_prod = MagicMock()
        mock_prod.id = 2
        mock_prod.price = 2499.0
        mock_db.query.return_value.filter.return_value.first.return_value = mock_prod

        detail = validator.verify_scenario_c_volatile_isolation(mock_db, product_id=2)
        assert detail.passed is True, f"Expected Scenario C to pass, violations: {detail.violations}"
        print("[PASS] Check 3: Scenario C verified volatile price isolation from embeddings")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 3: Scenario C volatile isolation: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 4: Scenario D — Inactive product isolation
    # --------------------------------------------------------------------------
    try:
        validator = SystemIntegrationValidator()
        mock_db = MagicMock()
        detail = validator.verify_scenario_d_inactive_isolation(mock_db, product_id=2)
        assert detail.passed is True, f"Expected Scenario D to pass, violations: {detail.violations}"
        print("[PASS] Check 4: Scenario D verified inactive products strictly excluded")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 4: Scenario D inactive isolation: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 5: Scenario E — Search -> RAG consistency
    # --------------------------------------------------------------------------
    try:
        mock_search = MagicMock()
        mock_item = MagicMock()
        mock_item.product.id = 2
        mock_item.match_reasons = ["exact_brand"]
        mock_search.search.return_value.results = [mock_item]

        mock_rag_ret = MagicMock()
        mock_rag_prod = MagicMock()
        mock_rag_prod.product_id = 2
        mock_rag_prod.search_match_context = ["exact_brand"]
        mock_bundle = MagicMock()
        mock_bundle.products = [mock_rag_prod]
        mock_rag_ret.retrieve_and_hydrate.return_value = (mock_bundle, MagicMock())

        validator = SystemIntegrationValidator(
            hybrid_search_service=mock_search,
            rag_retrieval_service=mock_rag_ret
        )
        mock_db = MagicMock()
        detail = validator.verify_scenario_e_search_rag_consistency(mock_db, product_id=2)
        assert detail.passed is True, f"Expected Scenario E to pass, violations: {detail.violations}"
        print("[PASS] Check 5: Scenario E verified search -> RAG candidate and state consistency")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 5: Scenario E consistency: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 6: Scenario F — Recommendation catalog consistency
    # --------------------------------------------------------------------------
    try:
        mock_rec_svc = MagicMock()
        mock_rec_item = MagicMock()
        mock_rec_item.product.id = 5
        mock_rec_item.product.status = "ACTIVE"
        mock_rec_item.product.price = 1999.0
        mock_rec_resp = MagicMock()
        mock_rec_resp.recommendations = [mock_rec_item]
        mock_rec_svc.get_recommendations.return_value = mock_rec_resp

        validator = SystemIntegrationValidator(recommendation_service=mock_rec_svc)
        mock_db = MagicMock()
        mock_db_prod = MagicMock()
        mock_db_prod.id = 5
        mock_db_prod.price = 1999.0
        mock_db.query.return_value.filter.return_value.first.return_value = mock_db_prod

        detail = validator.verify_scenario_f_recommendation_consistency(mock_db, product_id=2)
        assert detail.passed is True, f"Expected Scenario F to pass, violations: {detail.violations}"
        print("[PASS] Check 6: Scenario F verified recommendation catalog consistency")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 6: Scenario F consistency: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 7: Invalid citation triggers hard-gate failure
    # --------------------------------------------------------------------------
    try:
        evaluator = HardCorrectnessGateEvaluator()
        res = evaluator.evaluate(invalid_citations=2)
        assert res.passed is False
        assert res.total_violations == 2
        assert any("citation" in r.lower() for r in res.failure_reasons)
        print("[PASS] Check 7: Invalid citation strictly fails the hard correctness gate")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 7: Invalid citation gate check: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 8: Hard-filter violation triggers hard-gate failure
    # --------------------------------------------------------------------------
    try:
        evaluator = HardCorrectnessGateEvaluator()
        res = evaluator.evaluate(hard_filter_violations=1)
        assert res.passed is False
        assert res.total_violations == 1
        assert any("filter" in r.lower() for r in res.failure_reasons)
        print("[PASS] Check 8: Hard-filter violation strictly fails the hard correctness gate")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 8: Hard-filter gate check: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 9: Unaccepted metadata leak triggers hard-gate failure
    # --------------------------------------------------------------------------
    try:
        evaluator = HardCorrectnessGateEvaluator()
        res = evaluator.evaluate(unaccepted_metadata_leaks=1)
        assert res.passed is False
        assert res.total_violations == 1
        assert any("unaccepted" in r.lower() for r in res.failure_reasons)
        print("[PASS] Check 9: Unaccepted metadata leak strictly fails the hard correctness gate")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 9: Unaccepted metadata gate check: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 10: Recommendation self-return triggers hard-gate failure
    # --------------------------------------------------------------------------
    try:
        evaluator = HardCorrectnessGateEvaluator()
        res = evaluator.evaluate(recommendation_self_returns=1)
        assert res.passed is False
        assert res.total_violations == 1
        assert any("self-return" in r.lower() for r in res.failure_reasons)
        print("[PASS] Check 10: Recommendation self-return strictly fails the hard correctness gate")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 10: Self-return gate check: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 11: Component quality metrics remain strictly independent
    # --------------------------------------------------------------------------
    try:
        comp_metrics = SystemQualityMetrics()
        # Verify no blended or aggregate score attribute exists on the model
        assert not hasattr(comp_metrics, "platform_accuracy")
        assert not hasattr(comp_metrics, "overall_quality_score")
        assert hasattr(comp_metrics, "search")
        assert hasattr(comp_metrics, "rag")
        assert hasattr(comp_metrics, "recommendations")
        assert hasattr(comp_metrics, "embeddings")
        print("[PASS] Check 11: Component quality metrics remain strictly independent (zero artificial aggregate score)")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 11: Quality metrics independence: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 12: Operational metrics collection (P50/P95/P99 latency)
    # --------------------------------------------------------------------------
    try:
        lats = [10.0, 15.0, 20.0, 25.0, 30.0, 100.0]
        percentiles = compute_percentiles(lats)
        assert percentiles.p50_ms == 22.5
        assert percentiles.p95_ms > 30.0
        assert percentiles.p99_ms > percentiles.p95_ms
        assert percentiles.mean_ms == 33.33
        print("[PASS] Check 12: Operational metrics correctly compute P50/P95/P99 latency percentiles")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 12: Operational metrics: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 13: Strict status semantics: PASSED, FAILED, and ERROR
    # --------------------------------------------------------------------------
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="sys_eval_test_"))
        try:
            runner = SystemEvaluationRunner(results_dir=tmp_dir)

            # 1. Simulate PASSED run
            mock_integ = MagicMock()
            mock_integ.run_all_scenarios.return_value = SystemIntegrationSummary(all_passed=True, scenarios={})
            mock_comp = MagicMock()
            mock_comp.evaluate_all.return_value = SystemQualityMetrics()
            mock_ops = MagicMock()
            mock_ops.collect.return_value = SystemOperationalMetrics()
            runner.integration_validator = mock_integ
            runner.component_evaluator = mock_comp
            runner.operational_collector = mock_ops

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.count.return_value = 5

            art_pass = runner.run(db=mock_db, save_artifact=False)
            assert art_pass.overall_status == "PASSED"

            # 2. Simulate FAILED run (hard gate violation)
            mock_integ_fail = MagicMock()
            bad_scenario = ScenarioCheckDetail(
                scenario_name="Test",
                description="Test",
                passed=False,
                checks_performed=1,
                violations=["Invalid citation detected: image 999"]
            )
            mock_integ_fail.run_all_scenarios.return_value = SystemIntegrationSummary(
                all_passed=False,
                scenarios={"test": bad_scenario}
            )
            runner.integration_validator = mock_integ_fail
            art_fail = runner.run(db=mock_db, save_artifact=False)
            assert art_fail.overall_status == "FAILED"
            assert art_fail.hard_correctness_gates.passed is False

            # 3. Simulate ERROR run (catastrophic evaluator exception)
            mock_integ_crash = MagicMock()
            mock_integ_crash.run_all_scenarios.side_effect = RuntimeError("Database offline during evaluation")
            runner.integration_validator = mock_integ_crash
            art_err = runner.run(db=mock_db, save_artifact=False)
            assert art_err.overall_status == "ERROR"
            assert len(art_err.errors) > 0

            print("[PASS] Check 13: Evaluation runner strictly distinguishes PASSED, FAILED, and ERROR semantics")
            passed += 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception as e:
        print(f"[FAIL] Check 13: Status semantics: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 14: Immutable versioned artifact saved with latest_system.json pointer
    # --------------------------------------------------------------------------
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="sys_eval_artifact_"))
        try:
            runner = SystemEvaluationRunner(results_dir=tmp_dir)
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.count.return_value = 2

            mock_integ = MagicMock()
            mock_integ.run_all_scenarios.return_value = SystemIntegrationSummary(all_passed=True, scenarios={})
            mock_comp = MagicMock()
            mock_comp.evaluate_all.return_value = SystemQualityMetrics()
            mock_ops = MagicMock()
            mock_ops.collect.return_value = SystemOperationalMetrics()
            runner.integration_validator = mock_integ
            runner.component_evaluator = mock_comp
            runner.operational_collector = mock_ops

            art = runner.run(db=mock_db, save_artifact=True)

            # Check that immutable run_id file exists
            run_file = tmp_dir / f"{art.run_id}.json"
            assert run_file.exists(), f"Immutable run file {run_file} was not saved"

            # Check that latest_system.json exists
            latest_file = tmp_dir / "latest_system.json"
            assert latest_file.exists(), f"Pointer {latest_file} was not saved"

            # Check content parity
            with open(run_file, "r", encoding="utf-8") as f1, open(latest_file, "r", encoding="utf-8") as f2:
                d1 = json.load(f1)
                d2 = json.load(f2)
                assert d1["run_id"] == d2["run_id"]
                assert d1["evaluation_version"] == "system_v1"

            print("[PASS] Check 14: Immutable versioned artifact and latest_system.json pointer persisted cleanly")
            passed += 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception as e:
        print(f"[FAIL] Check 14: Artifact persistence: {e}")
        failed += 1

    print("=" * 70)
    print(f"RESULTS: {passed}/{total} checks passed, {failed} failed.")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_all_checks()
