"""MySQL Candidate Retriever for Phase 07 Hybrid Search.

Implements Q57, Q59, Q61:
- Structured candidate retrieval using MySQL B-Tree indexes
- Pre-filters by brand, category, price, and active catalog status
- Text matching on title/description for keyword relevance
- Returns candidate product IDs up to configurable K
"""

import logging
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.product import Product
from app.schemas.search import SearchFilters, SearchQuery
from app.search.filters import FilterRegistry

logger = logging.getLogger(__name__)


class MySQLCandidateRetriever:
    """Retrieves candidate product IDs from MySQL using structured pre-filtering."""

    def __init__(self, filter_registry: Optional[FilterRegistry] = None):
        self.registry = filter_registry or FilterRegistry()

    def retrieve_candidates(
        self,
        db: Session,
        search_query: SearchQuery,
        limit: int = 100
    ) -> list[int]:
        """Queries MySQL for product IDs satisfying structured filters and keyword relevance."""
        filters: SearchFilters = search_query.filters

        # 1. Base query: only ACTIVE products
        query = db.query(Product.id).filter(Product.status == "ACTIVE")

        # 2. Apply Brand pre-filter
        if filters.brand:
            query = query.filter(func.lower(Product.brand) == filters.brand.lower())

        # 3. Apply Category pre-filter
        if filters.category_id:
            query = query.filter(Product.category_id == filters.category_id)

        # 4. Apply Price pre-filters
        if filters.min_price is not None:
            query = query.filter(Product.price >= filters.min_price)
        if filters.max_price is not None:
            query = query.filter(Product.price <= filters.max_price)

        # 5. Apply Color / Size pre-filters if present
        if filters.color:
            color_handler = self.registry.get_handler("color")
            if color_handler:
                query = color_handler.apply_prefilter(query, filters.color)

        if filters.size:
            size_handler = self.registry.get_handler("size")
            if size_handler:
                query = size_handler.apply_prefilter(query, filters.size)

        # 6. Keyword relevance pre-filter (if semantic query has meaningful words)
        sem_query = search_query.semantic_query.strip()
        if sem_query:
            words = [w for w in sem_query.split() if len(w) > 2]
            if words:
                word_clauses = [
                    or_(
                        Product.title.ilike(f"%{w}%"),
                        Product.description.ilike(f"%{w}%")
                    )
                    for w in words[:4]  # Limit to first 4 content words to avoid query explosion
                ]
                # Match at least one word for lexical candidate gathering
                query = query.filter(or_(*word_clauses))

        # Order by newest/ID descending as stable fallback and limit
        candidate_rows = query.order_by(Product.id.desc()).limit(limit).all()
        candidate_ids = [row[0] for row in candidate_rows]

        logger.debug(f"MySQL pre-filter retrieved {len(candidate_ids)} candidate IDs (limit={limit})")
        return candidate_ids
