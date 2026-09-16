"""Recommendation Signals Calculation.

Implements Q90:
- Computes deterministic, normalized affinity signals in [0, 1] between source and candidate:
  * semantic_similarity (from FAISS cosine score)
  * category_affinity (exact category match)
  * brand_affinity (brand matching with neutral fallback)
  * price_similarity (relative price proximity ratio)
  * attribute_overlap (normalized accepted AI attribute matches)
- Zero external AI or LLM dependencies.
"""

from typing import Any, Optional

from app.models.product import Product
from app.rag.citation_validator import normalize_value
from app.schemas.recommendation import RecommendationCandidateSignals


def normalize_str(s: Optional[str]) -> str:
    """Normalizes string for robust equality checking."""
    return s.strip().lower() if s else ""


class RecommendationSignalsCalculator:
    """Calculates normalized constituent affinity signals between source and candidate products."""

    def compute_signals(
        self,
        source_product: Product,
        candidate_product: Product,
        semantic_score: float = 0.0,
        source_metadata: Optional[dict[str, Any]] = None,
        candidate_metadata: Optional[dict[str, Any]] = None
    ) -> RecommendationCandidateSignals:
        """Computes all constituent recommendation signals strictly normalized to [0, 1]."""
        # 1. Semantic similarity
        sem_sim = max(0.0, min(1.0, float(semantic_score)))

        # 2. Category affinity
        cat_aff = 0.0
        if source_product.category_id and candidate_product.category_id:
            if source_product.category_id == candidate_product.category_id:
                cat_aff = 1.0

        # 3. Brand affinity
        src_brand = normalize_str(source_product.brand)
        cand_brand = normalize_str(candidate_product.brand)
        if src_brand and cand_brand:
            brand_aff = 1.0 if src_brand == cand_brand else 0.0
        else:
            brand_aff = 0.2  # Neutral baseline when brand is unknown

        # 4. Price proximity
        price_sim = 0.0
        p_src = float(source_product.price or 0.0)
        p_cand = float(candidate_product.price or 0.0)
        if p_src > 0.0 and p_cand > 0.0:
            price_sim = min(p_src, p_cand) / max(p_src, p_cand)
            price_sim = max(0.0, min(1.0, price_sim))

        # 5. Attribute overlap
        attr_overlap = 0.0
        src_attrs = (source_metadata or {}).get("attributes", {})
        cand_attrs = (candidate_metadata or {}).get("attributes", {})

        if isinstance(src_attrs, dict) and isinstance(cand_attrs, dict) and src_attrs and cand_attrs:
            shared_keys = set(src_attrs.keys()) & set(cand_attrs.keys())
            if shared_keys:
                matches = 0
                for k in shared_keys:
                    s_node = src_attrs[k]
                    c_node = cand_attrs[k]
                    s_val = s_node.get("value") if isinstance(s_node, dict) else s_node
                    c_val = c_node.get("value") if isinstance(c_node, dict) else c_node
                    if normalize_value(s_val) == normalize_value(c_val) and s_val is not None:
                        matches += 1
                attr_overlap = matches / len(shared_keys)
                attr_overlap = max(0.0, min(1.0, attr_overlap))

        return RecommendationCandidateSignals(
            semantic_similarity=round(sem_sim, 4),
            category_affinity=round(cat_aff, 4),
            attribute_overlap=round(attr_overlap, 4),
            price_similarity=round(price_sim, 4),
            brand_affinity=round(brand_aff, 4)
        )
