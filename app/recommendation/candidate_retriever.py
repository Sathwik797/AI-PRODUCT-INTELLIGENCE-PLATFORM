"""Parallel Candidate Retriever for Phase 08 Recommendations.

Implements Q89:
- FAISSCandidateRetriever: Semantic nearest neighbors from dense index.
- MySQLCandidateRetriever: Structured catalog contextual candidates.
- ParallelCandidateUnion: Parallel execution via ThreadPoolExecutor.
  * NEVER shares a SQLAlchemy Session across threads (creates dedicated sessions with try/finally).
  * Explicit graceful degradation: if one source fails, the other continues.
  * If BOTH sources fail, raises RecommendationRetrievalError rather than returning misleading empty lists.
"""

import concurrent.futures
import logging
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.product import Product
from app.models.product_embedding import ProductEmbedding
from app.schemas.product_embedding import EmbeddingStatus
from app.schemas.recommendation import RecommendationConfig
from app.vector_store.base import VectorStore
from app.vector_store.faiss_store import FAISSVectorStore

logger = logging.getLogger(__name__)


class RecommendationRetrievalError(Exception):
    """Raised when recommendation candidate retrieval fails catastrophically."""
    pass


class FAISSRecommendationRetriever:
    """Retrieves semantic nearest neighbors for a source product from FAISS."""

    def __init__(self, vector_store: Optional[VectorStore] = None):
        self.vector_store = vector_store or FAISSVectorStore()

    def retrieve_candidates(
        self,
        db: Session,
        source_product_id: int,
        limit: int = 50
    ) -> list[tuple[int, float]]:
        """Finds semantic nearest neighbors for source product.

        Returns:
            list of (product_id, normalized_similarity_score)
        """
        # 1. Lookup source product embedding
        emb_record = (
            db.query(ProductEmbedding)
            .filter(
                ProductEmbedding.product_id == source_product_id,
                ProductEmbedding.status == EmbeddingStatus.READY.value
            )
            .first()
        )
        if not emb_record:
            logger.debug(f"Source product {source_product_id} has no READY embedding record.")
            return []

        # 2. Retrieve vector from FAISS
        source_vec = self.vector_store.get_vector(emb_record.vector_id)
        if source_vec is None:
            logger.debug(f"Source product {source_product_id} vector_id {emb_record.vector_id} not found in index.")
            return []

        # 3. Search index for top K + 1 (to account for self-match)
        search_hits = self.vector_store.search(source_vec, top_k=limit + 1)
        if not search_hits:
            return []

        hit_vector_ids = [vid for vid, _ in search_hits]
        hit_scores = {vid: score for vid, score in search_hits}

        # 4. Resolve hit vector_ids -> product_ids
        embedding_rows = (
            db.query(ProductEmbedding.vector_id, ProductEmbedding.product_id)
            .filter(
                ProductEmbedding.vector_id.in_(hit_vector_ids),
                ProductEmbedding.status == EmbeddingStatus.READY.value
            )
            .all()
        )
        vector_to_product = {vid: pid for vid, pid in embedding_rows}

        # 5. Assemble candidates excluding self
        candidates: list[tuple[int, float]] = []
        for vid, score in search_hits:
            pid = vector_to_product.get(vid)
            if pid is not None and pid != source_product_id:
                # Clamp cosine similarity from [-1, 1] to [0, 1]
                norm_score = max(0.0, min(1.0, float(score)))
                candidates.append((pid, norm_score))

        return candidates[:limit]


class MySQLRecommendationRetriever:
    """Retrieves structured catalog candidates matching category, brand, or price band."""

    def retrieve_candidates(
        self,
        db: Session,
        source_product: Product,
        limit: int = 50
    ) -> list[int]:
        """Queries contextual candidates from relational MySQL catalog.

        Returns:
            list of candidate product IDs
        """
        clauses = []

        # Same category
        if source_product.category_id:
            clauses.append(Product.category_id == source_product.category_id)

        # Same brand
        if source_product.brand and source_product.brand.strip():
            clauses.append(Product.brand == source_product.brand.strip())

        # Price proximity (within 50% to 200% of source price)
        if source_product.price and source_product.price > 0:
            min_p = source_product.price * 0.5
            max_p = source_product.price * 2.0
            clauses.append(Product.price.between(min_p, max_p))

        query = db.query(Product.id).filter(
            Product.status == "ACTIVE",
            Product.id != source_product.id
        )

        if clauses:
            query = query.filter(or_(*clauses))

        # Order and limit
        rows = query.order_by(Product.id.desc()).limit(limit).all()
        return [r[0] for r in rows]


class ParallelCandidateUnion:
    """Coordinates parallel candidate retrieval from FAISS and MySQL with graceful degradation."""

    def __init__(
        self,
        faiss_retriever: Optional[FAISSRecommendationRetriever] = None,
        mysql_retriever: Optional[MySQLRecommendationRetriever] = None,
        config: Optional[RecommendationConfig] = None
    ):
        self.faiss_retriever = faiss_retriever or FAISSRecommendationRetriever()
        self.mysql_retriever = mysql_retriever or MySQLRecommendationRetriever()
        self.config = config or RecommendationConfig()

    def gather_candidates(
        self,
        source_product: Product
    ) -> tuple[dict[int, float], dict[int, set[str]], bool]:
        """Gathers candidates in parallel using dedicated DB sessions per thread.

        Returns:
            Tuple of:
            - semantic_scores: dict[product_id, float]
            - candidate_provenance: dict[product_id, set[str]]
            - degraded_mode: bool (True if one branch failed)

        Raises:
            RecommendationRetrievalError: If BOTH retrieval branches fail.
        """
        source_id = source_product.id
        k = self.config.candidate_k

        faiss_candidates: list[tuple[int, float]] = []
        mysql_candidates: list[int] = []

        faiss_error: Optional[Exception] = None
        mysql_error: Optional[Exception] = None

        def _fetch_faiss():
            # Dedicated DB session for thread safety
            s = SessionLocal()
            try:
                return self.faiss_retriever.retrieve_candidates(s, source_id, limit=k)
            finally:
                s.close()

        def _fetch_mysql():
            # Dedicated DB session for thread safety
            s = SessionLocal()
            try:
                # Reload source product in thread session
                p = s.query(Product).filter(Product.id == source_id).first()
                if not p:
                    return []
                return self.mysql_retriever.retrieve_candidates(s, p, limit=k)
            finally:
                s.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut_faiss = executor.submit(_fetch_faiss)
            fut_mysql = executor.submit(_fetch_mysql)

            try:
                faiss_candidates = fut_faiss.result()
            except Exception as e:
                logger.warning(f"FAISS candidate retrieval failed for product {source_id}: {e}")
                faiss_error = e

            try:
                mysql_candidates = fut_mysql.result()
            except Exception as e:
                logger.warning(f"MySQL candidate retrieval failed for product {source_id}: {e}")
                mysql_error = e

        # Surface failure if BOTH sources failed
        if faiss_error is not None and mysql_error is not None:
            raise RecommendationRetrievalError(
                f"Both FAISS and MySQL recommendation candidate retrievals failed: "
                f"FAISS: {faiss_error}; MySQL: {mysql_error}"
            )

        degraded_mode = (faiss_error is not None) or (mysql_error is not None)

        # Merge candidate union
        semantic_scores: dict[int, float] = {}
        candidate_provenance: dict[int, set[str]] = {}

        for pid, score in faiss_candidates:
            semantic_scores[pid] = score
            candidate_provenance.setdefault(pid, set()).add("faiss")

        for pid in mysql_candidates:
            candidate_provenance.setdefault(pid, set()).add("mysql")

        return semantic_scores, candidate_provenance, degraded_mode
