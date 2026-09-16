"""Hybrid Ranker Strategy for Phase 07 Search.

Implements Q58, Q62:
- Linear weighted combination: FinalScore = α * S_semantic + β * S_structured
- Both components strictly normalized to [0, 1]
- Deterministic explainable match reasons
- Slices top N results
"""

import logging
import re
from typing import Any, Optional

from app.models.product import Product
from app.schemas.product import ProductResponse
from app.schemas.search import HybridSearchConfig, SearchFilters, SearchQuery, SearchResultItem

logger = logging.getLogger(__name__)


class HybridRanker:
    """Calculates normalized hybrid relevance scores and orders eligible products."""

    def __init__(self, config: Optional[HybridSearchConfig] = None):
        self.config = config or HybridSearchConfig()

    def compute_structured_score(
        self,
        product: Product,
        search_query: SearchQuery,
        accepted_metadata: dict[str, Any]
    ) -> float:
        """Computes a normalized structured relevance score in [0, 1]."""
        score = 0.0
        filters = search_query.filters

        # 1. Exact Brand match (0.25)
        if filters.brand:
            if product.brand and product.brand.strip().lower() == filters.brand.strip().lower():
                score += 0.25
        else:
            # Neutral baseline if no brand filter
            score += 0.15

        # 2. Category match (0.25)
        if filters.category_id:
            if product.category_id == filters.category_id:
                score += 0.25
        else:
            score += 0.15

        # 3. Lexical / Title token overlap with semantic query (0.50)
        sem_tokens = set(re.findall(r"\w+", search_query.semantic_query.lower()))
        # Remove common short words
        sem_tokens = {t for t in sem_tokens if len(t) > 2}
        if sem_tokens:
            prod_text = f"{product.title or ''} {product.description or ''}".lower()
            matched_tokens = sum(1 for t in sem_tokens if t in prod_text)
            token_ratio = matched_tokens / len(sem_tokens)
            score += 0.50 * min(1.0, token_ratio)
        else:
            score += 0.30

        return max(0.0, min(1.0, score))

    def derive_match_reasons(
        self,
        product: Product,
        search_query: SearchQuery,
        semantic_score: Optional[float],
        provenance: set[str]
    ) -> list[str]:
        """Generates deterministic, verified match reasons."""
        reasons: list[str] = []
        filters: SearchFilters = search_query.filters

        # Semantic signal
        if "faiss" in provenance and (semantic_score is not None and semantic_score >= 0.50):
            reasons.append("semantic_match")

        # Hard filter match signals
        if filters.brand and product.brand and product.brand.strip().lower() == filters.brand.strip().lower():
            reasons.append("exact_brand")

        if filters.category_id and product.category_id == filters.category_id:
            reasons.append("category_match")

        if filters.min_price is not None or filters.max_price is not None:
            reasons.append("price_constraint")

        if filters.color:
            reasons.append("color_match")

        if filters.size:
            reasons.append("size_match")

        # Lexical keyword match signal
        sem_tokens = set(re.findall(r"\w+", search_query.semantic_query.lower()))
        if sem_tokens:
            prod_title = (product.title or "").lower()
            if any(t in prod_title for t in sem_tokens if len(t) > 2):
                reasons.append("lexical_match")

        return sorted(set(reasons))

    def rank(
        self,
        eligible_products: dict[int, Product],
        semantic_scores: dict[int, float],
        candidate_provenance: dict[int, set[str]],
        search_query: SearchQuery,
        accepted_metadata_map: dict[int, dict[str, Any]],
        limit: int = 20
    ) -> list[SearchResultItem]:
        """Ranks eligible products by weighted hybrid score and returns top N items."""
        ranked_items: list[SearchResultItem] = []

        alpha = self.config.semantic_weight
        beta = self.config.structured_weight

        for pid, product in eligible_products.items():
            sem_score = semantic_scores.get(pid, 0.0)
            meta = accepted_metadata_map.get(pid, {})

            struct_score = self.compute_structured_score(product, search_query, meta)

            # Final linear combination
            final_score = (alpha * sem_score) + (beta * struct_score)
            # Bound strictly to [0.0, 1.0]
            final_score = round(max(0.0, min(1.0, float(final_score))), 4)

            provenance = candidate_provenance.get(pid, set())
            reasons = self.derive_match_reasons(product, search_query, sem_score, provenance)

            ranked_items.append(
                SearchResultItem(
                    product=ProductResponse.model_validate(product),
                    score=final_score,
                    match_reasons=reasons
                )
            )

        # Sort descending by final score
        ranked_items.sort(key=lambda item: item.score, reverse=True)

        return ranked_items[:limit]
