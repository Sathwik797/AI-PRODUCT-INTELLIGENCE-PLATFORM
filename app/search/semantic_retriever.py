"""FAISS Semantic Candidate Retriever for Phase 07 Hybrid Search.

Implements Q55, Q57, Q59:
- Uses existing EmbeddingProvider port to embed SearchQuery.semantic_query
- Queries VectorStore for top K nearest dense vectors
- Resolves position-independent vector_id -> product_id using ProductEmbedding
- Caches query vector within a search operation for zero-cost bounded K expansion
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.ai.embedding_provider import EmbeddingProvider, GoogleGeminiEmbeddingProvider
from app.models.product_embedding import ProductEmbedding
from app.schemas.product_embedding import EmbeddingStatus
from app.vector_store.base import VectorStore
from app.vector_store.faiss_store import FAISSVectorStore

logger = logging.getLogger(__name__)


class SemanticCandidateRetriever:
    """Retrieves semantically similar product candidates using dense vector search."""

    def __init__(
        self,
        embedding_provider: Optional[EmbeddingProvider] = None,
        vector_store: Optional[VectorStore] = None
    ):
        self.provider = embedding_provider or GoogleGeminiEmbeddingProvider()
        self.vector_store = vector_store or FAISSVectorStore()

    def retrieve_candidates(
        self,
        db: Session,
        semantic_query: str,
        limit: int = 100,
        cached_query_vector: Optional[list[float]] = None
    ) -> tuple[list[tuple[int, float]], list[float]]:
        """Searches vector store for top K candidates.

        Returns:
            (list of (product_id, similarity_score), query_vector)
        """
        if not semantic_query or not semantic_query.strip():
            return [], []

        # 1. Obtain query vector (reusing cached vector if expanding K)
        if cached_query_vector is not None:
            query_vector = cached_query_vector
        else:
            query_vector = self.provider.embed_text(semantic_query.strip())

        # 2. Query VectorStore
        search_hits = self.vector_store.search(query_vector, top_k=limit)
        if not search_hits:
            return [], query_vector

        hit_vector_ids = [vid for vid, _ in search_hits]
        hit_scores = {vid: score for vid, score in search_hits}

        # 3. Batch resolve vector_id -> product_id via MySQL authoritative embeddings
        embedding_rows = (
            db.query(ProductEmbedding.vector_id, ProductEmbedding.product_id)
            .filter(
                ProductEmbedding.vector_id.in_(hit_vector_ids),
                ProductEmbedding.status == EmbeddingStatus.READY.value
            )
            .all()
        )

        vector_to_product = {vid: pid for vid, pid in embedding_rows}

        # 4. Assemble resolved (product_id, similarity_score) maintaining FAISS rank order
        product_candidates: list[tuple[int, float]] = []
        for vid, score in search_hits:
            if vid in vector_to_product:
                pid = vector_to_product[vid]
                # Normalized cosine similarity: FAISS inner product on unit vectors is [-1, 1],
                # clamped to [0, 1] for relevance scoring
                norm_score = max(0.0, min(1.0, float(score)))
                product_candidates.append((pid, norm_score))

        logger.debug(
            f"FAISS retrieved {len(search_hits)} vector hits, resolved {len(product_candidates)} "
            f"READY product candidates (limit={limit})"
        )
        return product_candidates, query_vector
