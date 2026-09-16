"""Hybrid Search Orchestration Service for Phase 07.

Implements Q54, Q57, Q58, Q59, Q60, Q61, Q62:
- Query Understanding -> Typed SearchQuery
- Parallel Candidate Retrieval (MySQL + FAISS)
- Candidate Union (C = C_mysql ∪ C_faiss)
- Final Eligibility Guard on live MySQL state
- Bounded K Expansion with cached query vector (zero redundant API calls)
- HybridRanker scoring and match reason derivation
- SearchResponse assembly with telemetry and optional debug diagnostics
"""

import concurrent.futures
import logging
import time
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.product import Product
from app.schemas.search import (
    HybridSearchConfig,
    SearchMetadata,
    SearchQuery,
    SearchResponse,
    SearchResultItem,
)
from app.search.eligibility_guard import FinalEligibilityGuard
from app.search.mysql_retriever import MySQLCandidateRetriever
from app.search.query_parser import DeterministicQueryParser, QueryParserPort
from app.search.ranker import HybridRanker
from app.search.semantic_retriever import SemanticCandidateRetriever

logger = logging.getLogger(__name__)


class HybridSearchService:
    """Orchestrates hybrid e-commerce search combining structured SQL and dense FAISS vectors."""

    def __init__(
        self,
        query_parser: Optional[QueryParserPort] = None,
        mysql_retriever: Optional[MySQLCandidateRetriever] = None,
        semantic_retriever: Optional[SemanticCandidateRetriever] = None,
        eligibility_guard: Optional[FinalEligibilityGuard] = None,
        ranker: Optional[HybridRanker] = None,
        config: Optional[HybridSearchConfig] = None
    ):
        self.config = config or HybridSearchConfig()
        self.query_parser = query_parser or DeterministicQueryParser()
        self.mysql_retriever = mysql_retriever or MySQLCandidateRetriever()
        self.semantic_retriever = semantic_retriever or SemanticCandidateRetriever()
        self.eligibility_guard = eligibility_guard or FinalEligibilityGuard()
        self.ranker = ranker or HybridRanker(config=self.config)

    def search(
        self,
        db: Session,
        raw_query: str,
        limit: Optional[int] = None,
        debug: bool = False
    ) -> SearchResponse:
        """Executes end-to-end hybrid search for a user query."""
        start_time = time.perf_counter()
        requested_limit = limit if limit is not None else self.config.default_limit

        # 1. Query Understanding (Q54, Q55)
        search_query: SearchQuery = self.query_parser.parse(raw_query, db=db)

        # 2. Parallel Candidate Retrieval (Q57, Q59)
        k_sql = self.config.mysql_candidate_k
        k_faiss = self.config.faiss_candidate_k

        mysql_candidates: list[int] = []
        faiss_candidates: list[tuple[int, float]] = []
        cached_query_vector: list[float] = []

        # Execute candidate retrieval concurrently using independent DB sessions
        def _fetch_mysql():
            s = SessionLocal()
            try:
                return self.mysql_retriever.retrieve_candidates(s, search_query, limit=k_sql)
            finally:
                s.close()

        def _fetch_faiss():
            s = SessionLocal()
            try:
                return self.semantic_retriever.retrieve_candidates(
                    s,
                    search_query.semantic_query,
                    limit=k_faiss
                )
            finally:
                s.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut_sql = executor.submit(_fetch_mysql)
            fut_faiss = executor.submit(_fetch_faiss)
            mysql_candidates = fut_sql.result()
            faiss_candidates, cached_query_vector = fut_faiss.result()

        # 3. Candidate Union & Provenance Tracking (Q57)
        candidate_provenance: dict[int, set[str]] = {}
        semantic_scores: dict[int, float] = {}

        for pid in mysql_candidates:
            candidate_provenance.setdefault(pid, set()).add("mysql")

        for pid, score in faiss_candidates:
            candidate_provenance.setdefault(pid, set()).add("faiss")
            semantic_scores[pid] = score

        union_candidate_ids = list(candidate_provenance.keys())

        # 4. Final Eligibility Guard on Live Database State (Q61)
        eligible_products, metadata_map = self.eligibility_guard.filter_eligible_candidates(
            db,
            union_candidate_ids,
            search_query
        )

        # 5. Bounded K Expansion if eligible count is below requested limit (Q60)
        k_expanded = False
        initial_eligible_count = len(eligible_products)

        if len(eligible_products) < requested_limit and self.config.enable_expansion:
            # Check if expansion is viable (did either branch hit its initial K limit?)
            can_expand_sql = len(mysql_candidates) >= k_sql
            can_expand_faiss = len(faiss_candidates) >= k_faiss

            if can_expand_sql or can_expand_faiss:
                max_k = self.config.max_candidate_k
                k_expanded = True
                logger.info(
                    f"Bounded K expansion triggered: eligible={len(eligible_products)} < {requested_limit}. "
                    f"Expanding candidate pool up to {max_k}."
                )

                expanded_sql_ids: list[int] = []
                expanded_faiss_candidates: list[tuple[int, float]] = []

                if can_expand_sql:
                    expanded_sql_ids = self.mysql_retriever.retrieve_candidates(db, search_query, limit=max_k)
                if can_expand_faiss:
                    expanded_faiss_candidates, _ = self.semantic_retriever.retrieve_candidates(
                        db,
                        search_query.semantic_query,
                        limit=max_k,
                        cached_query_vector=cached_query_vector  # Zero provider re-calls
                    )

                # Track new candidates
                new_candidate_ids: list[int] = []
                for pid in expanded_sql_ids:
                    candidate_provenance.setdefault(pid, set()).add("mysql")
                    if pid not in eligible_products:
                        new_candidate_ids.append(pid)

                for pid, score in expanded_faiss_candidates:
                    candidate_provenance.setdefault(pid, set()).add("faiss")
                    semantic_scores[pid] = score
                    if pid not in eligible_products:
                        new_candidate_ids.append(pid)

                if new_candidate_ids:
                    new_eligible, new_meta = self.eligibility_guard.filter_eligible_candidates(
                        db,
                        list(set(new_candidate_ids)),
                        search_query
                    )
                    eligible_products.update(new_eligible)
                    metadata_map.update(new_meta)

        # 6. Hybrid Ranking & Match Reason Generation (Q58, Q62)
        ranked_results: list[SearchResultItem] = self.ranker.rank(
            eligible_products=eligible_products,
            semantic_scores=semantic_scores,
            candidate_provenance=candidate_provenance,
            search_query=search_query,
            accepted_metadata_map=metadata_map,
            limit=requested_limit
        )

        took_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        # 7. Metadata Assembly
        metadata = SearchMetadata(
            eligible_candidate_count=len(eligible_products),
            total_eligible=len(eligible_products),
            returned_count=len(ranked_results),
            requested_limit=requested_limit,
            took_ms=took_ms,
            k_expanded=k_expanded,
            parsed_filters=search_query.filters,
            semantic_query=search_query.semantic_query
        )

        # 8. Optional Debug Diagnostics (Q62)
        debug_diagnostics: Optional[dict[str, Any]] = None
        if debug:
            debug_diagnostics = {
                "mysql_candidate_count": len(mysql_candidates),
                "faiss_candidate_count": len(faiss_candidates),
                "union_candidate_count": len(union_candidate_ids),
                "initial_eligible_count": initial_eligible_count,
                "final_eligible_count": len(eligible_products),
                "k_expanded": k_expanded,
                "initial_k": {"mysql": k_sql, "faiss": k_faiss},
                "max_k": self.config.max_candidate_k,
                "candidate_provenance_summary": {
                    "mysql_only": sum(1 for p in candidate_provenance.values() if p == {"mysql"}),
                    "faiss_only": sum(1 for p in candidate_provenance.values() if p == {"faiss"}),
                    "both": sum(1 for p in candidate_provenance.values() if p == {"mysql", "faiss"}),
                },
                "candidate_ids": {
                    "mysql": mysql_candidates,
                    "faiss": [pid for pid, _ in faiss_candidates],
                    "union": union_candidate_ids,
                }
            }

        return SearchResponse(
            query=raw_query,
            results=ranked_results,
            metadata=metadata,
            debug_diagnostics=debug_diagnostics
        )
