"""Shared mathematical metrics engine and independent constraint validator for Step 07.1.

Implements Q65, Q67:
- Standardized DCG, IDCG, NDCG@K (with logarithmic discounting)
- MRR (first item with relevance grade >= 1)
- Recall@K and HitRate@K for candidate stages
- Independent Hard-Constraint Validator (Zero-tolerance correctness boundary)
- Strict ground-truth immutability: Never rewrites benchmark relevance labels
- Deterministic percentile calculations for P50, P95, P99
- Explicit handling of zero-result/negative queries (no NaNs, no polluted ranking metrics)
"""

import math
import re
from typing import Any, Optional

from app.schemas.product import ProductResponse
from app.schemas.search import SearchFilters
from app.search.filters import extract_attribute_value_str


def calculate_dcg(relevances: list[int], k: int) -> float:
    """Calculates Discounted Cumulative Gain at K with logarithmic discounting.
    
    Formula: sum_{i=0}^{k-1} (2^{rel_i} - 1) / log2(i + 2)
    """
    dcg = 0.0
    for idx, rel in enumerate(relevances[:k]):
        if rel > 0:
            dcg += (2.0 ** rel - 1.0) / math.log2(idx + 2.0)
    return dcg


def calculate_idcg(ideal_relevances: list[int], k: int) -> float:
    """Calculates Ideal Discounted Cumulative Gain at K."""
    sorted_rels = sorted(ideal_relevances, reverse=True)
    return calculate_dcg(sorted_rels, k)


def calculate_ndcg_at_k(
    returned_ids: list[int],
    ground_truth: dict[int, int],
    k: int
) -> Optional[float]:
    """Calculates Normalized Discounted Cumulative Gain at K.
    
    Returns:
        float in [0.0, 1.0] if there are positive ground-truth items,
        or None if no positive ground-truth items exist (e.g., zero-result queries).
    """
    positive_ground_truth = [rel for rel in ground_truth.values() if rel > 0]
    if not positive_ground_truth:
        return None  # Undefined for queries with zero relevant items

    relevances = [ground_truth.get(pid, 0) for pid in returned_ids[:k]]
    dcg = calculate_dcg(relevances, k)
    idcg = calculate_idcg(positive_ground_truth, k)

    if idcg <= 0.0:
        return 0.0
    return min(1.0, max(0.0, dcg / idcg))


def calculate_mrr(
    returned_ids: list[int],
    ground_truth: dict[int, int]
) -> Optional[float]:
    """Calculates Mean Reciprocal Rank (first result with relevance grade >= 1).
    
    Returns:
        1.0 / rank (1-based) if found, 0.0 if not found,
        or None if no positive ground-truth items exist.
    """
    has_positive = any(rel >= 1 for rel in ground_truth.values())
    if not has_positive:
        return None

    for rank, pid in enumerate(returned_ids, start=1):
        if ground_truth.get(pid, 0) >= 1:
            return 1.0 / rank
    return 0.0


def calculate_recall_at_k(
    retrieved_ids: list[int],
    ground_truth: dict[int, int],
    k: int
) -> Optional[float]:
    """Calculates Recall@K: retrieved relevant items / total relevant items.
    
    Returns None if ground truth contains no relevant items.
    """
    relevant_ids = {pid for pid, rel in ground_truth.items() if rel >= 1}
    if not relevant_ids:
        return None

    retrieved_set = set(retrieved_ids[:k])
    hits = len(relevant_ids.intersection(retrieved_set))
    return hits / float(len(relevant_ids))


def calculate_hit_rate_at_k(
    retrieved_ids: list[int],
    ground_truth: dict[int, int],
    k: int
) -> Optional[float]:
    """Calculates HitRate@K: 1.0 if >=1 relevant item retrieved, else 0.0.
    
    Returns None if ground truth contains no relevant items.
    """
    relevant_ids = {pid for pid, rel in ground_truth.items() if rel >= 1}
    if not relevant_ids:
        return None

    retrieved_set = set(retrieved_ids[:k])
    return 1.0 if len(relevant_ids.intersection(retrieved_set)) > 0 else 0.0


class IndependentHardConstraintValidator:
    """Evaluates returned products against explicit query constraints (Q65, Q67).
    
    INVARIANT:
    Operates strictly independently of benchmark ground truth.
    Never alters, overrides, or mutates ground-truth relevance grades.
    """

    @staticmethod
    def validate_product(
        product: Any,
        expected_constraints: SearchFilters,
        accepted_metadata: Optional[dict[str, Any]] = None
    ) -> list[str]:
        """Validates a product against explicit constraints.
        
        Returns a list of violation descriptions (empty if fully compliant).
        """
        violations = []

        # 1. Active Status Constraint
        status = getattr(product, "status", None)
        if status is not None and str(status).upper() != "ACTIVE":
            violations.append(f"Status '{status}' is not ACTIVE")

        # 2. Brand Constraint
        if expected_constraints.brand:
            prod_brand = getattr(product, "brand", None)
            if not prod_brand or expected_constraints.brand.lower() not in prod_brand.lower():
                violations.append(f"Brand '{prod_brand}' does not match '{expected_constraints.brand}'")

        # 3. Category Constraint
        if expected_constraints.category:
            cat_name = ""
            category_rel = getattr(product, "category", None)
            if category_rel and hasattr(category_rel, "name") and isinstance(category_rel.name, str):
                cat_name = category_rel.name
            elif getattr(product, "category_name", None) and isinstance(product.category_name, str):
                cat_name = product.category_name

            if cat_name and expected_constraints.category.lower() not in cat_name.lower():
                violations.append(f"Category '{cat_name}' does not match '{expected_constraints.category}'")

        # 4. Price Constraints (Exact violation semantics per approval)
        prod_price = getattr(product, "price", None)
        if prod_price is not None:
            # min_price violation: product.price < expected min_price
            if expected_constraints.min_price is not None and float(prod_price) < float(expected_constraints.min_price):
                violations.append(
                    f"min_price violation: product.price ({prod_price}) < expected min_price ({expected_constraints.min_price})"
                )
            # max_price violation: product.price > expected max_price
            if expected_constraints.max_price is not None and float(prod_price) > float(expected_constraints.max_price):
                violations.append(
                    f"max_price violation: product.price ({prod_price}) > expected max_price ({expected_constraints.max_price})"
                )

        # 5. Color Constraint against accepted AI metadata or title/desc
        if expected_constraints.color:
            target_color = expected_constraints.color.lower().strip()
            matched = False
            if accepted_metadata:
                attrs = accepted_metadata.get("attributes", accepted_metadata)
                color_val = extract_attribute_value_str(attrs.get("color"))
                if color_val:
                    pattern = r'\b' + re.escape(target_color) + r'\b'
                    if re.search(pattern, color_val.lower()):
                        matched = True
            if not matched:
                # Fallback to title/desc if product text contains color
                prod_text = f"{getattr(product, 'title', '') or ''} {getattr(product, 'description', '') or ''}"
                pattern = r'\b' + re.escape(target_color) + r'\b'
                if re.search(pattern, prod_text.lower()):
                    matched = True

            if not matched:
                violations.append(f"Color constraint '{expected_constraints.color}' not satisfied in metadata")

        # 6. Size Constraint against accepted AI metadata or title/desc
        if expected_constraints.size:
            target_size = expected_constraints.size.lower().strip()
            matched = False
            if accepted_metadata:
                attrs = accepted_metadata.get("attributes", accepted_metadata)
                size_val = extract_attribute_value_str(attrs.get("size"))
                if size_val:
                    pattern = r'(?:^|\b|\s)' + re.escape(target_size) + r'(?:$|\b|\s)'
                    if re.search(pattern, size_val.lower()):
                        matched = True
            if not matched:
                prod_text = f"{getattr(product, 'title', '') or ''} {getattr(product, 'description', '') or ''}"
                pattern = r'(?:^|\b|\s)' + re.escape(target_size) + r'(?:$|\b|\s)'
                if re.search(pattern, prod_text.lower()):
                    matched = True

            if not matched:
                violations.append(f"Size constraint '{expected_constraints.size}' not satisfied in metadata")

        return violations


def calculate_percentiles(values: list[float]) -> tuple[float, float, float]:
    """Calculates P50, P95, P99 deterministically.
    
    Handles small sample sizes gracefully without NaN errors.
    """
    if not values:
        return (0.0, 0.0, 0.0)

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def _get_pct(p: float) -> float:
        if n == 1:
            return round(sorted_vals[0], 2)
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return round(sorted_vals[int(k)], 2)
        d0 = sorted_vals[f] * (c - k)
        d1 = sorted_vals[c] * (k - f)
        return round(d0 + d1, 2)

    return (_get_pct(0.50), _get_pct(0.95), _get_pct(0.99))
