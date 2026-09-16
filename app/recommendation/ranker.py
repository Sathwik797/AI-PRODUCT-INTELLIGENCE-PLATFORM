"""Recommendation Ranker Strategy.

Implements Q91:
- Configurable weighted combination of constituent signals:
  score = w_semantic * S_semantic
        + w_category * S_category
        + w_attribute * S_attribute
        + w_price * S_price
        + w_brand * S_brand
- Strictly normalized and bounded in [0.0, 1.0].
- Deterministic, explainable match reason derivation.
- Free of DB and network calls.
"""

from typing import Optional

from app.models.product import Product
from app.schemas.recommendation import (
    RecommendationCandidateSignals,
    RecommendationConfig,
)


class RecommendationRanker:
    """Ranks recommendation candidates by configurable weighted combination of affinity signals."""

    def __init__(self, config: Optional[RecommendationConfig] = None):
        self.config = config or RecommendationConfig()

    def compute_score(self, signals: RecommendationCandidateSignals) -> float:
        """Calculates normalized hybrid recommendation score in [0, 1]."""
        raw_score = (
            (self.config.semantic_weight * signals.semantic_similarity)
            + (self.config.category_weight * signals.category_affinity)
            + (self.config.attribute_weight * signals.attribute_overlap)
            + (self.config.price_weight * signals.price_similarity)
            + (self.config.brand_weight * signals.brand_affinity)
        )
        return round(max(0.0, min(1.0, float(raw_score))), 4)

    def derive_match_reasons(self, signals: RecommendationCandidateSignals) -> list[str]:
        """Derives deterministic, explainable match reasons from underlying signals."""
        reasons: list[str] = []

        if signals.semantic_similarity >= 0.70:
            reasons.append("high_semantic_similarity")

        if signals.category_affinity >= 0.99:
            reasons.append("same_category")

        if signals.brand_affinity >= 0.99:
            reasons.append("same_brand")

        if signals.attribute_overlap >= 0.40:
            reasons.append("matching_attributes")

        if signals.price_similarity >= 0.80:
            reasons.append("similar_price")

        return sorted(reasons)

    def rank(
        self,
        evaluated_candidates: list[tuple[Product, RecommendationCandidateSignals]]
    ) -> list[tuple[Product, float, list[str]]]:
        """Ranks candidates descending by computed recommendation score.

        Returns:
            list of (Product, score, match_reasons)
        """
        ranked: list[tuple[Product, float, list[str]]] = []

        for prod, sigs in evaluated_candidates:
            score = self.compute_score(sigs)
            reasons = self.derive_match_reasons(sigs)
            ranked.append((prod, score, reasons))

        # Sort descending by score; break ties by product ID descending for determinism
        ranked.sort(key=lambda item: (item[1], item[0].id), reverse=True)
        return ranked
