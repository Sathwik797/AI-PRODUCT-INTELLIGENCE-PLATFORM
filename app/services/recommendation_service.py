"""Recommendation Orchestration Service for Phase 08.

Implements Q88, Q89, Q90, Q91, Q92, Q93:
- Orchestrates:
  1. Source Product Existence Check
  2. Parallel Candidate Generation (FAISS + MySQL) with Graceful Degradation
  3. Hard Eligibility Gates (ACTIVE, not self, exists)
  4. Constituent Signal Calculation
  5. RecommendationRanker Weighted Scoring
  6. Duplicate & Near-Duplicate Suppression
  7. Assembly of RecommendationResponse with telemetry
"""

import logging
import time
from typing import Any, Optional
import numpy as np
from sqlalchemy.orm import Session

from app.models.ai_generation import AIGeneration
from app.models.product import Product
from app.models.product_embedding import ProductEmbedding
from app.models.product_metadata import ProductMetadata
from app.recommendation.candidate_retriever import (
    ParallelCandidateUnion,
    RecommendationRetrievalError,
)
from app.recommendation.dedup import DuplicateSuppressor
from app.recommendation.ranker import RecommendationRanker
from app.recommendation.signals import RecommendationSignalsCalculator
from app.schemas.product import ProductResponse
from app.schemas.product_embedding import EmbeddingStatus
from app.schemas.recommendation import (
    RecommendationConfig,
    RecommendationItem,
    RecommendationMetadata,
    RecommendationResponse,
)
from app.vector_store.base import VectorStore
from app.vector_store.faiss_store import FAISSVectorStore

logger = logging.getLogger(__name__)


class ProductNotFoundError(Exception):
    """Raised when the source product does not exist."""
    pass


class RecommendationService:
    """Service coordinating end-to-end hybrid product recommendations."""

    def __init__(
        self,
        candidate_union: Optional[ParallelCandidateUnion] = None,
        signals_calculator: Optional[RecommendationSignalsCalculator] = None,
        ranker: Optional[RecommendationRanker] = None,
        suppressor: Optional[DuplicateSuppressor] = None,
        vector_store: Optional[VectorStore] = None,
        config: Optional[RecommendationConfig] = None
    ):
        self.config = config or RecommendationConfig()
        self.candidate_union = candidate_union or ParallelCandidateUnion(config=self.config)
        self.signals_calculator = signals_calculator or RecommendationSignalsCalculator()
        self.ranker = ranker or RecommendationRanker(config=self.config)
        self.suppressor = suppressor or DuplicateSuppressor(
            similarity_threshold=self.config.similarity_dedup_threshold
        )
        self.vector_store = vector_store or FAISSVectorStore()

    def get_recommendations(
        self,
        db: Session,
        product_id: int,
        limit: Optional[int] = None
    ) -> RecommendationResponse:
        """Computes hybrid recommendations for the specified product.

        Args:
            db: Active SQLAlchemy database session.
            product_id: Target source product primary key.
            limit: Maximum recommendations requested.

        Returns:
            RecommendationResponse with ranked recommendations and telemetry.

        Raises:
            ProductNotFoundError: If source product does not exist.
            RecommendationRetrievalError: If BOTH retrieval branches fail.
        """
        start_time = time.perf_counter()
        req_limit = limit if limit is not None else self.config.default_limit
        req_limit = max(1, min(self.config.max_limit, req_limit))

        # 1. Source Product Existence Check
        source_product = db.query(Product).filter(Product.id == product_id).first()
        if not source_product:
            raise ProductNotFoundError(f"Product with id {product_id} not found.")

        # 2. Parallel Candidate Retrieval (FAISS + MySQL)
        semantic_scores, candidate_provenance, degraded_mode = (
            self.candidate_union.gather_candidates(source_product)
        )

        faiss_count = sum(1 for pids in candidate_provenance.values() if "faiss" in pids)
        mysql_count = sum(1 for pids in candidate_provenance.values() if "mysql" in pids)

        # 3. Hard Eligibility Gates (Q90)
        # Exclude source product explicitly
        candidate_ids = [pid for pid in candidate_provenance.keys() if pid != product_id]

        if not candidate_ids:
            took_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            return RecommendationResponse(
                source_product_id=product_id,
                recommendations=[],
                metadata=RecommendationMetadata(
                    source_product_id=product_id,
                    evaluated_candidates=0,
                    returned_count=0,
                    took_ms=took_ms,
                    faiss_candidate_count=faiss_count,
                    mysql_candidate_count=mysql_count,
                    degraded_mode=degraded_mode
                )
            )

        # Query database for ACTIVE candidates only
        eligible_products = (
            db.query(Product)
            .filter(
                Product.id.in_(candidate_ids),
                Product.status == "ACTIVE",
                Product.id != product_id
            )
            .all()
        )

        if not eligible_products:
            took_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            return RecommendationResponse(
                source_product_id=product_id,
                recommendations=[],
                metadata=RecommendationMetadata(
                    source_product_id=product_id,
                    evaluated_candidates=0,
                    returned_count=0,
                    took_ms=took_ms,
                    faiss_candidate_count=faiss_count,
                    mysql_candidate_count=mysql_count,
                    degraded_mode=degraded_mode
                )
            )

        # 4. Hydrate accepted AI metadata for source and candidates
        all_product_ids = [product_id] + [p.id for p in eligible_products]
        accepted_meta_map = self._batch_get_accepted_metadata(db, all_product_ids)
        source_meta = accepted_meta_map.get(product_id, {})

        # 5. Compute Signals for each eligible candidate
        evaluated_pairs = []
        for cand in eligible_products:
            sem_score = semantic_scores.get(cand.id, 0.0)
            cand_meta = accepted_meta_map.get(cand.id, {})
            signals = self.signals_calculator.compute_signals(
                source_product=source_product,
                candidate_product=cand,
                semantic_score=sem_score,
                source_metadata=source_meta,
                candidate_metadata=cand_meta
            )
            evaluated_pairs.append((cand, signals))

        # 6. Rank Candidates
        ranked_items = self.ranker.rank(evaluated_pairs)

        # 7. Collect Candidate Dense Vectors for Deduplication
        cand_pids = [item[0].id for item in ranked_items]
        product_vectors = self._get_product_vectors(db, cand_pids)

        # 8. Duplicate / Similarity Suppression (Q92)
        distinct_items = self.suppressor.suppress(
            ranked_items=ranked_items,
            product_vectors=product_vectors,
            limit=req_limit
        )

        # 9. Format RecommendationItems
        recommendations = [
            RecommendationItem(
                product=ProductResponse.model_validate(prod),
                score=score,
                match_reasons=reasons
            )
            for prod, score, reasons in distinct_items
        ]

        took_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        metadata = RecommendationMetadata(
            source_product_id=product_id,
            evaluated_candidates=len(eligible_products),
            returned_count=len(recommendations),
            took_ms=took_ms,
            faiss_candidate_count=faiss_count,
            mysql_candidate_count=mysql_count,
            degraded_mode=degraded_mode
        )

        return RecommendationResponse(
            source_product_id=product_id,
            recommendations=recommendations,
            metadata=metadata
        )

    def _batch_get_accepted_metadata(
        self,
        db: Session,
        product_ids: list[int]
    ) -> dict[int, dict[str, Any]]:
        """Retrieves accepted AI metadata attributes for a batch of products."""
        if not product_ids:
            return {}

        meta_rows = (
            db.query(ProductMetadata.product_id, ProductMetadata.current_generation_id)
            .filter(
                ProductMetadata.product_id.in_(product_ids),
                ProductMetadata.current_generation_id.isnot(None)
            )
            .all()
        )

        gen_id_to_pid = {gid: pid for pid, gid in meta_rows if gid is not None}
        if not gen_id_to_pid:
            return {}

        gen_rows = (
            db.query(AIGeneration)
            .filter(AIGeneration.id.in_(list(gen_id_to_pid.keys())))
            .all()
        )

        result: dict[int, dict[str, Any]] = {}
        for gen in gen_rows:
            pid = gen_id_to_pid.get(gen.id)
            if not pid or not gen.output or not gen.acceptance_state:
                continue
            acc_state = gen.acceptance_state
            # Only include attributes if accepted or modified
            if acc_state.get("attributes") in ("accepted", "modified"):
                result[pid] = {
                    "attributes": gen.output.get("attributes", {})
                }

        return result

    def _get_product_vectors(
        self,
        db: Session,
        product_ids: list[int]
    ) -> dict[int, np.ndarray]:
        """Retrieves unit-normalized dense vectors from FAISS for deduplication."""
        if not product_ids:
            return {}

        emb_rows = (
            db.query(ProductEmbedding.product_id, ProductEmbedding.vector_id)
            .filter(
                ProductEmbedding.product_id.in_(product_ids),
                ProductEmbedding.status == EmbeddingStatus.READY.value
            )
            .all()
        )

        vectors: dict[int, np.ndarray] = {}
        for pid, vid in emb_rows:
            vec = self.vector_store.get_vector(vid)
            if vec is not None:
                vectors[pid] = vec

        return vectors
