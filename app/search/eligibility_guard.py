"""Final Eligibility Guard for Phase 07 Hybrid Search.

Implements Q57, Q61, Q64:
- Performs single-roundtrip batch hydration of candidate union products
- Authoritative correctness boundary: evaluates hard constraints against MySQL live state
- Re-checks active status, brand, category, price range, color, and size
- Strictly eliminates any candidate violating an explicit constraint
- Avoids N+1 queries via batch metadata hydration
"""

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.ai_generation import AIGeneration
from app.models.product import Product
from app.models.product_metadata import ProductMetadata
from app.schemas.search import SearchFilters, SearchQuery
from app.search.filters import FilterRegistry

logger = logging.getLogger(__name__)


def extract_accepted_attributes(generation: Optional[AIGeneration]) -> dict[str, Any]:
    """Extracts accepted/modified discovery attributes from an AIGeneration record."""
    if not generation or not generation.output or not generation.acceptance_state:
        return {}
    acc_state = generation.acceptance_state
    if acc_state.get("attributes") in ("accepted", "modified"):
        return generation.output.get("attributes", {})
    return {}


class FinalEligibilityGuard:
    """Correctness boundary enforcing hard business constraints on candidate union."""

    def __init__(self, filter_registry: Optional[FilterRegistry] = None):
        self.registry = filter_registry or FilterRegistry()

    def filter_eligible_candidates(
        self,
        db: Session,
        candidate_ids: list[int],
        search_query: SearchQuery
    ) -> tuple[dict[int, Product], dict[int, dict[str, Any]]]:
        """Hydrates candidates in a single batch query and evaluates all hard filters.

        Returns:
            (eligible_products_by_id, accepted_metadata_by_id)
        """
        if not candidate_ids:
            return {}, {}

        filters: SearchFilters = search_query.filters

        # 1. Single batch query for canonical Product records (must be ACTIVE)
        products = (
            db.query(Product)
            .filter(
                Product.id.in_(candidate_ids),
                Product.status == "ACTIVE"
            )
            .all()
        )

        if not products:
            return {}, {}

        # 2. Batch hydrate ProductMetadata and AIGeneration if color or size filters are active
        need_metadata = bool(filters.color or filters.size)
        metadata_by_product: dict[int, dict[str, Any]] = {}

        if need_metadata:
            meta_records = (
                db.query(ProductMetadata)
                .options(joinedload(ProductMetadata.current_generation))
                .filter(ProductMetadata.product_id.in_(candidate_ids))
                .all()
            )
            for m in meta_records:
                attrs = extract_accepted_attributes(m.current_generation)
                metadata_by_product[m.product_id] = {"attributes": attrs}

        # 3. Apply Hard Eligibility Verification
        eligible_products: dict[int, Product] = {}
        for p in products:
            meta = metadata_by_product.get(p.id, {})

            # Hard Constraint A: Price Bounds
            if filters.min_price is not None and p.price < filters.min_price:
                continue
            if filters.max_price is not None and p.price > filters.max_price:
                continue

            # Hard Constraint B: Brand
            if filters.brand:
                if not p.brand or p.brand.strip().lower() != filters.brand.strip().lower():
                    continue

            # Hard Constraint C: Category
            if filters.category_id:
                if p.category_id != filters.category_id:
                    continue

            # Hard Constraint D: Color
            if filters.color:
                color_handler = self.registry.get_handler("color")
                if color_handler and not color_handler.matches_product(p, filters.color, meta):
                    continue

            # Hard Constraint E: Size
            if filters.size:
                size_handler = self.registry.get_handler("size")
                if size_handler and not size_handler.matches_product(p, filters.size, meta):
                    continue

            eligible_products[p.id] = p

        logger.debug(
            f"Eligibility Guard: {len(eligible_products)} / {len(candidate_ids)} candidates passed."
        )
        return eligible_products, metadata_by_product
