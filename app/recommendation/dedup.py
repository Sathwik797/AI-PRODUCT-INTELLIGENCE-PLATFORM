"""Duplicate & Near-Duplicate Suppression for Recommendations.

Implements Q92:
- Simple, deterministic duplicate suppression preventing top N from being near-clones.
- Checks:
  1. Identical normalized product titles.
  2. Pairwise cosine similarity >= similarity_dedup_threshold between candidate vectors.
- Continues with the next highest-ranked eligible candidate.
"""

from typing import Any, Optional
import numpy as np

from app.models.product import Product


def normalize_title(title: Optional[str]) -> str:
    """Normalizes title string for exact title deduplication."""
    return title.strip().lower() if title else ""


class DuplicateSuppressor:
    """Filters near-duplicate recommendation items while preserving ranking order."""

    def __init__(self, similarity_threshold: float = 0.95):
        self.similarity_threshold = similarity_threshold

    def suppress(
        self,
        ranked_items: list[tuple[Product, float, list[str]]],
        product_vectors: Optional[dict[int, np.ndarray]] = None,
        limit: int = 5
    ) -> list[tuple[Product, float, list[str]]]:
        """Slices top N distinct items, skipping near-duplicates of higher-ranked items.

        Args:
            ranked_items: Pre-sorted (Product, score, match_reasons) descending by score.
            product_vectors: Optional map of product_id -> unit-normalized numpy vector.
            limit: Maximum distinct recommendations to return.

        Returns:
            list of distinct (Product, score, match_reasons) up to limit.
        """
        accepted: list[tuple[Product, float, list[str]]] = []
        vectors = product_vectors or {}

        for item in ranked_items:
            cand_prod = item[0]
            cand_title = normalize_title(cand_prod.title)
            cand_vec = vectors.get(cand_prod.id)

            is_duplicate = False

            for acc_item in accepted:
                acc_prod = acc_item[0]
                acc_title = normalize_title(acc_prod.title)

                # 1. Exact title duplication
                if cand_title and acc_title and cand_title == acc_title:
                    is_duplicate = True
                    break

                # 2. Pairwise dense cosine similarity check
                acc_vec = vectors.get(acc_prod.id)
                if cand_vec is not None and acc_vec is not None:
                    # Vectors are L2-normalized float32 arrays
                    dot_product = float(np.dot(cand_vec.flatten(), acc_vec.flatten()))
                    if dot_product >= self.similarity_threshold:
                        is_duplicate = True
                        break

            if not is_duplicate:
                accepted.append(item)
                if len(accepted) >= limit:
                    break

        return accepted
