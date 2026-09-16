"""RAG Retrieval & Knowledge Hydration Service.

Implements Q71, Q72, Q75, Q76, Q79:
- Delegates candidate discovery to existing HybridSearchService.
- Respects configurable context size limit (default top 5).
- Reuses Phase 05 acceptance semantics: loads active AIGeneration via ProductMetadata.
- Extracts live canonical state (price, status), canonical product facts, and accepted AI attributes.
- Preserves singular evidence provenance (source_type, image_id, explanation).
- Isolates search match reasons as retrieval provenance (NOT factual catalog truth).
- Produces typed RAGKnowledgeBundle read-time projection.
"""

import logging
from typing import Any, Optional
from sqlalchemy.orm import Session

from app.models.ai_generation import AIGeneration
from app.models.product import Product
from app.models.product_metadata import ProductMetadata
from app.schemas.rag import (
    RAGConfig,
    RAGEvidence,
    RAGKnowledgeBundle,
    RAGProductContext,
    RAGVerifiedAttribute,
)
from app.schemas.search import SearchResponse
from app.services.hybrid_search_service import HybridSearchService

logger = logging.getLogger(__name__)


class RAGRetrievalService:
    """Service responsible for retrieving and hydrating grounded RAG knowledge."""

    def __init__(
        self,
        hybrid_search_service: Optional[HybridSearchService] = None,
        config: Optional[RAGConfig] = None
    ):
        self.hybrid_search_service = hybrid_search_service or HybridSearchService()
        self.config = config or RAGConfig()

    def retrieve_and_hydrate(
        self,
        db: Session,
        question: str,
        limit: Optional[int] = None
    ) -> tuple[RAGKnowledgeBundle, SearchResponse]:
        """Discovers products via hybrid search and hydratively compiles a RAGKnowledgeBundle.

        Args:
            db: Active SQLAlchemy session.
            question: User's search/question query.
            limit: Optional override for max context products.

        Returns:
            Tuple of (RAGKnowledgeBundle, SearchResponse).
        """
        max_k = limit or self.config.max_context_products

        # 1. Delegate retrieval to existing HybridSearchService
        search_response: SearchResponse = self.hybrid_search_service.search(
            db=db,
            raw_query=question,
            limit=max_k
        )

        if not search_response.results:
            return RAGKnowledgeBundle(question=question, products=[]), search_response

        # 2. Bounded top K candidates
        selected_results = search_response.results[:max_k]

        product_contexts: list[RAGProductContext] = []
        for res_item in selected_results:
            prod_id = res_item.product.id
            match_reasons = res_item.match_reasons

            # Hydrate authoritative current catalog data
            context = self._hydrate_single_product(
                db=db,
                product_id=prod_id,
                match_reasons=match_reasons
            )
            if context:
                product_contexts.append(context)

        bundle = RAGKnowledgeBundle(
            question=question,
            products=product_contexts
        )
        return bundle, search_response

    def _hydrate_single_product(
        self,
        db: Session,
        product_id: int,
        match_reasons: list[str]
    ) -> Optional[RAGProductContext]:
        """Hydrates authoritative catalog state and accepted AI metadata for a single product."""
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return None

        # Live transactional facts directly from MySQL row
        live_catalog_state = {
            "price": float(product.price),
            "status": str(product.status),
        }

        # Canonical product facts
        category_name = product.category.name if product.category else None
        product_facts = {
            "title": product.title,
            "description": product.description,
            "brand": product.brand,
            "category": category_name,
        }

        # Active accepted AI metadata
        verified_attributes = self._extract_accepted_attributes(db, product_id)

        return RAGProductContext(
            product_id=product.id,
            live_catalog_state=live_catalog_state,
            product_facts=product_facts,
            verified_attributes=verified_attributes,
            search_match_context=list(match_reasons)
        )

    def _extract_accepted_attributes(
        self,
        db: Session,
        product_id: int
    ) -> list[RAGVerifiedAttribute]:
        """Extracts accepted AI metadata attributes reusing Phase 05 acceptance state semantics."""
        meta = (
            db.query(ProductMetadata)
            .filter(ProductMetadata.product_id == product_id)
            .first()
        )
        if not meta or not meta.current_generation_id:
            return []

        generation = (
            db.query(AIGeneration)
            .filter(AIGeneration.id == meta.current_generation_id)
            .first()
        )
        if not generation or not generation.output or not generation.acceptance_state:
            return []

        acc_state = generation.acceptance_state
        output = generation.output

        # Phase 05 acceptance check: only attributes marked 'accepted' or 'modified'
        if acc_state.get("attributes") not in ("accepted", "modified"):
            return []

        raw_attributes = output.get("attributes", {})
        if not isinstance(raw_attributes, dict):
            return []

        verified: list[RAGVerifiedAttribute] = []
        for attr_name, attr_node in raw_attributes.items():
            if not isinstance(attr_node, dict):
                continue

            attr_type = str(attr_node.get("type") or "text")
            attr_val = attr_node.get("value")
            unit = attr_node.get("unit")
            confidence = attr_node.get("confidence")

            # Extract singular evidence source
            evidence_obj: Optional[RAGEvidence] = None
            raw_ev = attr_node.get("evidence")
            if isinstance(raw_ev, dict):
                src = raw_ev.get("source") or {}
                src_type = src.get("type", "inferred")
                if src_type not in ("image", "seller", "inferred", "canonical_catalog"):
                    src_type = "inferred"
                image_id = src.get("image_id")
                expl = raw_ev.get("explanation")
                evidence_obj = RAGEvidence(
                    source_type=src_type,
                    image_id=image_id,
                    explanation=expl
                )

            verified.append(
                RAGVerifiedAttribute(
                    attribute=attr_name,
                    type=attr_type,
                    value=attr_val,
                    unit=unit,
                    confidence=confidence,
                    evidence=evidence_obj
                )
            )

        return verified
