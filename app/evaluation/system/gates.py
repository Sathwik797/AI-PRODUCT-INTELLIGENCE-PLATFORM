"""Hard Correctness Gate Evaluator for Phase 09.

Implements Q95:
- Strictly enforces non-negotiable correctness boundaries:
  1. invalid_citations == 0
  2. hard_filter_violations == 0
  3. inactive_product_leaks == 0
  4. unaccepted_metadata_leaks == 0
  5. recommendation_self_returns == 0
  6. canonical_data_inconsistencies == 0
- If ANY gate is violated, passed=False (status=FAILED).
- Never aggregates or averages violations into a weighted percentage.
"""

from typing import Optional

from app.schemas.system_evaluation import (
    HardCorrectnessGateResult,
    HardGateViolationCounts,
)


class HardCorrectnessGateEvaluator:
    """Evaluates non-negotiable correctness invariants across the platform."""

    def evaluate(
        self,
        invalid_citations: int = 0,
        hard_filter_violations: int = 0,
        inactive_product_leaks: int = 0,
        unaccepted_metadata_leaks: int = 0,
        recommendation_self_returns: int = 0,
        canonical_data_inconsistencies: int = 0,
        total_checks: int = 6,
        additional_reasons: Optional[list[str]] = None
    ) -> HardCorrectnessGateResult:
        """Evaluates violation counts and builds deterministic HardCorrectnessGateResult."""
        counts = HardGateViolationCounts(
            invalid_citations=max(0, invalid_citations),
            hard_filter_violations=max(0, hard_filter_violations),
            inactive_product_leaks=max(0, inactive_product_leaks),
            unaccepted_metadata_leaks=max(0, unaccepted_metadata_leaks),
            recommendation_self_returns=max(0, recommendation_self_returns),
            canonical_data_inconsistencies=max(0, canonical_data_inconsistencies)
        )

        total_violations = (
            counts.invalid_citations
            + counts.hard_filter_violations
            + counts.inactive_product_leaks
            + counts.unaccepted_metadata_leaks
            + counts.recommendation_self_returns
            + counts.canonical_data_inconsistencies
        )

        passed = (total_violations == 0)

        failure_reasons: list[str] = list(additional_reasons or [])
        if counts.invalid_citations > 0:
            failure_reasons.append(f"Detected {counts.invalid_citations} invalid/hallucinated citation(s).")
        if counts.hard_filter_violations > 0:
            failure_reasons.append(f"Detected {counts.hard_filter_violations} search hard-filter constraint violation(s).")
        if counts.inactive_product_leaks > 0:
            failure_reasons.append(f"Detected {counts.inactive_product_leaks} inactive/draft product leak(s) in downstream responses.")
        if counts.unaccepted_metadata_leaks > 0:
            failure_reasons.append(f"Detected {counts.unaccepted_metadata_leaks} unaccepted/rejected metadata leak(s) in authoritative state.")
        if counts.recommendation_self_returns > 0:
            failure_reasons.append(f"Detected {counts.recommendation_self_returns} recommendation self-return violation(s).")
        if counts.canonical_data_inconsistencies > 0:
            failure_reasons.append(f"Detected {counts.canonical_data_inconsistencies} canonical catalog propagation inconsistency(ies).")

        return HardCorrectnessGateResult(
            passed=passed,
            total_checks=max(total_checks, 6),
            total_violations=total_violations,
            violations=counts,
            failure_reasons=failure_reasons
        )
