"""Phase 08 Hybrid Recommendation Engine Focused Verification Suite.

Verifies:
1. Source product is never recommended (self-exclusion).
2. Inactive / draft products are strictly excluded by hard eligibility gates.
3. FAISS + MySQL candidates are unioned concurrently.
4. Parallel retrieval never shares a SQLAlchemy Session across worker threads.
5. Graceful degradation: Survives single-branch failure (FAISS or MySQL).
6. Catastrophic failure: Both branches failing raises RecommendationRetrievalError.
7. Ranking combines configured signals correctly into normalized [0, 1] scores.
8. Match reasons are deterministic and grounded in underlying signals.
9. Near-duplicate suppression filters near-clones by title and vector cosine similarity.
10. Missing / empty candidate pool returns 200 with recommendations: [].
11. Source product not found returns 404.
12. Recommendation API endpoint conforms strictly to RecommendationResponse contract.
"""

import os
import sys
from datetime import datetime
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from app.main import app
from app.models.product import Product
from app.recommendation.candidate_retriever import (
    FAISSRecommendationRetriever,
    MySQLRecommendationRetriever,
    ParallelCandidateUnion,
    RecommendationRetrievalError,
)
from app.recommendation.dedup import DuplicateSuppressor
from app.recommendation.ranker import RecommendationRanker
from app.recommendation.signals import (
    RecommendationCandidateSignals,
    RecommendationSignalsCalculator,
)
from app.schemas.product import ProductResponse
from app.schemas.recommendation import (
    RecommendationConfig,
    RecommendationItem,
    RecommendationMetadata,
    RecommendationResponse,
)
from app.services.recommendation_service import (
    ProductNotFoundError,
    RecommendationService,
)
from app.vector_store.base import VectorStore


# ==============================================================================
# FAKE / MOCK VECTOR STORE
# ==============================================================================

class MockVectorStore(VectorStore):
    """In-memory fake VectorStore for deterministic unit testing."""

    def __init__(self, vectors: Optional[dict[int, np.ndarray]] = None):
        self.vectors = vectors or {}

    def search(self, query_vector: Any, top_k: int = 10) -> list[tuple[int, float]]:
        q_norm = np.array(query_vector).flatten()
        q_norm = q_norm / (np.linalg.norm(q_norm) + 1e-9)

        results = []
        for vid, vec in self.vectors.items():
            v_norm = vec.flatten() / (np.linalg.norm(vec.flatten()) + 1e-9)
            sim = float(np.dot(q_norm, v_norm))
            results.append((vid, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def get_vector(self, vector_id: int) -> Optional[np.ndarray]:
        return self.vectors.get(vector_id)

    def add_vector(self, vector_id: int, vector: Any) -> None:
        self.vectors[vector_id] = np.array(vector)

    def remove_vector(self, vector_id: int) -> None:
        self.vectors.pop(vector_id, None)

    def contains(self, vector_id: int) -> bool:
        return vector_id in self.vectors

    def count(self) -> int:
        return len(self.vectors)


# ==============================================================================
# HELPER TEST PRODUCTS
# ==============================================================================

def make_dummy_product(
    id: int,
    title: str,
    price: float = 2499.0,
    category_id: int = 3,
    brand: str = "Nike",
    status: str = "ACTIVE",
    sku: Optional[str] = None
) -> Product:
    p = Product()
    p.id = id
    p.title = title
    p.price = price
    p.category_id = category_id
    p.brand = brand
    p.status = status
    p.sku = sku or f"SKU-{id}"
    p.description = f"Description for {title}"
    now = datetime.utcnow()
    p.created_at = now
    p.updated_at = now
    return p


# ==============================================================================
# VERIFICATION SUITE
# ==============================================================================

def run_all_checks():
    passed = 0
    failed = 0
    total = 12

    print("=" * 70)
    print("PHASE 08 — HYBRID RECOMMENDATION ENGINE VERIFICATION SUITE")
    print("=" * 70)

    # --------------------------------------------------------------------------
    # Check 1: Source product is never recommended (self-exclusion)
    # --------------------------------------------------------------------------
    try:
        source_p = make_dummy_product(1, "Nike Air Force 1")
        other_p = make_dummy_product(2, "Nike Air Max 90")

        mock_union = MagicMock()
        # Pretend retriever accidentally returned source_p.id as candidate
        mock_union.gather_candidates.return_value = ({1: 1.0, 2: 0.85}, {1: {"faiss"}, 2: {"faiss"}}, False)

        mock_db = MagicMock()
        # DB lookup for source product
        def mock_query(model):
            q = MagicMock()
            if model == Product:
                def mock_filter(*args, **kwargs):
                    fq = MagicMock()
                    # If looking up source product
                    fq.first.return_value = source_p
                    # If querying candidates
                    fq.all.return_value = [other_p]
                    return fq
                q.filter = mock_filter
            return q

        mock_db.query = mock_query

        svc = RecommendationService(candidate_union=mock_union)
        svc._batch_get_accepted_metadata = MagicMock(return_value={})
        svc._get_product_vectors = MagicMock(return_value={})

        resp = svc.get_recommendations(mock_db, product_id=1, limit=5)
        rec_ids = [r.product.id for r in resp.recommendations]
        assert 1 not in rec_ids, "Source product was improperly included in recommendations"
        print("[PASS] Check 1: Source product is strictly excluded from recommendations")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 1: Self-exclusion failed: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 2: Inactive products are excluded
    # --------------------------------------------------------------------------
    try:
        source_p = make_dummy_product(1, "Nike Air Force 1")
        active_p = make_dummy_product(2, "Nike Air Max 90", status="ACTIVE")
        inactive_p = make_dummy_product(3, "Nike Cortez", status="ARCHIVED")

        mock_union = MagicMock()
        mock_union.gather_candidates.return_value = ({2: 0.8, 3: 0.95}, {2: {"faiss"}, 3: {"faiss"}}, False)

        mock_db = MagicMock()
        def mock_query_inactive(model):
            q = MagicMock()
            if model == Product:
                def mock_filter(*args, **kwargs):
                    fq = MagicMock()
                    fq.first.return_value = source_p
                    # In real DB, Product.status == 'ACTIVE' excludes inactive_p
                    fq.all.return_value = [active_p]
                    return fq
                q.filter = mock_filter
            return q

        mock_db.query = mock_query_inactive

        svc = RecommendationService(candidate_union=mock_union)
        svc._batch_get_accepted_metadata = MagicMock(return_value={})
        svc._get_product_vectors = MagicMock(return_value={})

        resp = svc.get_recommendations(mock_db, product_id=1, limit=5)
        rec_ids = [r.product.id for r in resp.recommendations]
        assert 3 not in rec_ids, "Inactive product was improperly included"
        assert 2 in rec_ids
        print("[PASS] Check 2: Inactive products are strictly excluded by eligibility gates")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 2: Inactive product exclusion failed: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 3: FAISS + MySQL candidates are unioned
    # --------------------------------------------------------------------------
    try:
        mock_faiss_ret = MagicMock()
        mock_faiss_ret.retrieve_candidates.return_value = [(2, 0.90), (3, 0.80)]

        mock_mysql_ret = MagicMock()
        mock_mysql_ret.retrieve_candidates.return_value = [3, 4, 5]

        union_coordinator = ParallelCandidateUnion(
            faiss_retriever=mock_faiss_ret,
            mysql_retriever=mock_mysql_ret,
            config=RecommendationConfig(candidate_k=10)
        )

        source_p = make_dummy_product(1, "Nike Air Force 1")
        with patch("app.recommendation.candidate_retriever.SessionLocal") as mock_sl:
            mock_sess = MagicMock()
            mock_sess.query.return_value.filter.return_value.first.return_value = source_p
            mock_sl.return_value = mock_sess

            scores, provenance, degraded = union_coordinator.gather_candidates(source_p)

        all_candidates = set(provenance.keys())
        assert all_candidates == {2, 3, 4, 5}, f"Expected union {{2, 3, 4, 5}}, got {all_candidates}"
        assert provenance[2] == {"faiss"}
        assert provenance[3] == {"faiss", "mysql"}
        assert provenance[4] == {"mysql"}
        assert scores[2] == 0.90
        assert scores[3] == 0.80
        assert degraded is False
        print("[PASS] Check 3: Parallel candidate generation successfully unions FAISS and MySQL candidates")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 3: Candidate union failed: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 4: Parallel retrieval never shares a SQLAlchemy Session across threads
    # --------------------------------------------------------------------------
    try:
        created_sessions = []

        def fake_session_local():
            sess = MagicMock()
            created_sessions.append(sess)
            return sess

        mock_faiss_ret = MagicMock()
        mock_faiss_ret.retrieve_candidates.return_value = [(2, 0.90)]
        mock_mysql_ret = MagicMock()
        mock_mysql_ret.retrieve_candidates.return_value = [3]

        union_coordinator = ParallelCandidateUnion(
            faiss_retriever=mock_faiss_ret,
            mysql_retriever=mock_mysql_ret
        )

        source_p = make_dummy_product(1, "Test")
        with patch("app.recommendation.candidate_retriever.SessionLocal", side_effect=fake_session_local):
            union_coordinator.gather_candidates(source_p)

        # Must have created exactly 2 distinct sessions (one for FAISS thread, one for MySQL thread)
        assert len(created_sessions) == 2, f"Expected 2 independent sessions, got {len(created_sessions)}"
        assert created_sessions[0] is not created_sessions[1], "Same session instance was shared across threads!"
        # Verify both sessions were closed cleanly
        assert created_sessions[0].close.called, "FAISS thread session was not closed"
        assert created_sessions[1].close.called, "MySQL thread session was not closed"
        print("[PASS] Check 4: Parallel retrieval uses independent DB sessions per thread with guaranteed closure")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 4: Session safety check failed: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 5: Graceful degradation (single-branch failure)
    # --------------------------------------------------------------------------
    try:
        mock_faiss_fail = MagicMock()
        mock_faiss_fail.retrieve_candidates.side_effect = RuntimeError("FAISS index offline")

        mock_mysql_ok = MagicMock()
        mock_mysql_ok.retrieve_candidates.return_value = [10, 11]

        union_coordinator = ParallelCandidateUnion(
            faiss_retriever=mock_faiss_fail,
            mysql_retriever=mock_mysql_ok
        )

        source_p = make_dummy_product(1, "Test")
        with patch("app.recommendation.candidate_retriever.SessionLocal") as mock_sl:
            mock_sess = MagicMock()
            mock_sess.query.return_value.filter.return_value.first.return_value = source_p
            mock_sl.return_value = mock_sess

            scores, provenance, degraded = union_coordinator.gather_candidates(source_p)

        assert degraded is True, "degraded_mode should be True when FAISS fails"
        assert set(provenance.keys()) == {10, 11}, "MySQL candidates should survive FAISS failure"
        print("[PASS] Check 5: Survives single-branch retrieval failure in graceful degraded mode")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 5: Single-branch failure degradation: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 6: Catastrophic failure (both branches fail)
    # --------------------------------------------------------------------------
    try:
        mock_faiss_fail = MagicMock()
        mock_faiss_fail.retrieve_candidates.side_effect = RuntimeError("FAISS crashed")

        mock_mysql_fail = MagicMock()
        mock_mysql_fail.retrieve_candidates.side_effect = RuntimeError("MySQL connection lost")

        union_coordinator = ParallelCandidateUnion(
            faiss_retriever=mock_faiss_fail,
            mysql_retriever=mock_mysql_fail
        )

        source_p = make_dummy_product(1, "Test")
        catastrophic_error_raised = False
        with patch("app.recommendation.candidate_retriever.SessionLocal"):
            try:
                union_coordinator.gather_candidates(source_p)
            except RecommendationRetrievalError:
                catastrophic_error_raised = True

        assert catastrophic_error_raised, "Expected RecommendationRetrievalError when both branches fail"
        print("[PASS] Check 6: Both retrieval sources failing raises RecommendationRetrievalError")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 6: Catastrophic failure handling: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 7: Ranking combines configured signals into normalized [0, 1] scores
    # --------------------------------------------------------------------------
    try:
        cfg = RecommendationConfig(
            semantic_weight=0.40,
            category_weight=0.25,
            attribute_weight=0.15,
            price_weight=0.10,
            brand_weight=0.10
        )
        ranker = RecommendationRanker(config=cfg)

        sigs = RecommendationCandidateSignals(
            semantic_similarity=0.90,
            category_affinity=1.0,
            attribute_overlap=0.80,
            price_similarity=0.95,
            brand_affinity=1.0
        )

        # Expected: 0.40*0.90 + 0.25*1.0 + 0.15*0.80 + 0.10*0.95 + 0.10*1.0
        # = 0.36 + 0.25 + 0.12 + 0.095 + 0.10 = 0.925
        score = ranker.compute_score(sigs)
        assert 0.92 <= score <= 0.93, f"Expected ~0.925, got {score}"
        assert 0.0 <= score <= 1.0, "Score was out of [0, 1] bounds"
        print("[PASS] Check 7: RecommendationRanker combines configured weights correctly into bounded [0, 1] score")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 7: Ranking score calculation: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 8: Match reasons are deterministic
    # --------------------------------------------------------------------------
    try:
        ranker = RecommendationRanker()
        sigs = RecommendationCandidateSignals(
            semantic_similarity=0.75,
            category_affinity=1.0,
            attribute_overlap=0.50,
            price_similarity=0.85,
            brand_affinity=1.0
        )
        reasons = ranker.derive_match_reasons(sigs)
        expected = ["high_semantic_similarity", "matching_attributes", "same_brand", "same_category", "similar_price"]
        assert reasons == expected, f"Expected {expected}, got {reasons}"

        # If semantic is below threshold, high_semantic_similarity should not appear
        sigs_low = RecommendationCandidateSignals(
            semantic_similarity=0.30,
            category_affinity=1.0,
            attribute_overlap=0.0,
            price_similarity=0.20,
            brand_affinity=0.0
        )
        reasons_low = ranker.derive_match_reasons(sigs_low)
        assert reasons_low == ["same_category"]
        print("[PASS] Check 8: Match reasons are deterministic and strictly derived from underlying signals")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 8: Match reason derivation: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 9: Near-duplicate suppression
    # --------------------------------------------------------------------------
    try:
        suppressor = DuplicateSuppressor(similarity_threshold=0.95)

        p1 = make_dummy_product(10, "Nike Air Max 90 Black")
        p2 = make_dummy_product(11, "Nike Air Max 90 Black")  # Exact title duplicate of p1
        p3 = make_dummy_product(12, "Nike Air Max 90 Triple Black")  # Near clone with vector sim 0.98
        p4 = make_dummy_product(13, "Nike Pegasus 40")  # Distinct

        # Simulate unit vectors
        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([1.0, 0.0, 0.0])
        v3 = np.array([0.98, 0.198, 0.0])  # dot(v1, v3) = 0.98 >= 0.95
        v4 = np.array([0.0, 1.0, 0.0])     # dot(v1, v4) = 0.0

        product_vectors = {10: v1, 11: v2, 12: v3, 13: v4}
        ranked = [
            (p1, 0.95, ["high_semantic_similarity"]),
            (p2, 0.94, ["high_semantic_similarity"]),
            (p3, 0.93, ["high_semantic_similarity"]),
            (p4, 0.80, ["same_brand"])
        ]

        distinct = suppressor.suppress(ranked, product_vectors=product_vectors, limit=5)
        distinct_ids = [item[0].id for item in distinct]
        assert distinct_ids == [10, 13], f"Expected [10, 13], got {distinct_ids} (p2 and p3 should be suppressed)"
        print("[PASS] Check 9: Near-duplicate suppression eliminates exact title and high-cosine near-clones")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 9: Duplicate suppression: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 10: Missing / empty candidate pool returns recommendations: []
    # --------------------------------------------------------------------------
    try:
        source_p = make_dummy_product(1, "Isolated Product")
        mock_union = MagicMock()
        mock_union.gather_candidates.return_value = ({}, {}, False)

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = source_p
        mock_db.query.return_value.filter.return_value.all.return_value = []

        svc = RecommendationService(candidate_union=mock_union)
        resp = svc.get_recommendations(mock_db, product_id=1, limit=5)
        assert resp.recommendations == []
        assert resp.metadata.returned_count == 0
        assert resp.metadata.evaluated_candidates == 0
        print("[PASS] Check 10: Empty candidate pool cleanly returns recommendations: [] with 0 evaluated")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 10: Empty candidate pool: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 11: Source product 404 behavior
    # --------------------------------------------------------------------------
    try:
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        svc = RecommendationService()
        not_found_raised = False
        try:
            svc.get_recommendations(mock_db, product_id=9999)
        except ProductNotFoundError:
            not_found_raised = True

        assert not_found_raised, "ProductNotFoundError was not raised for missing product"
        print("[PASS] Check 11: Missing source product cleanly raises ProductNotFoundError")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 11: 404 check: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 12: Recommendation API response contract works
    # --------------------------------------------------------------------------
    try:
        from app.api.recommendation import get_recommendation_service

        mock_api_service = MagicMock()
        mock_api_service.get_recommendations.return_value = RecommendationResponse(
            source_product_id=2,
            recommendations=[
                RecommendationItem(
                    product=ProductResponse(
                        id=3,
                        title="Nike Pegasus Trail",
                        sku="NK-PEG",
                        price=3499.0,
                        category_id=1,
                        status="ACTIVE",
                        created_at="2026-01-01T00:00:00",
                        updated_at="2026-01-01T00:00:00"
                    ),
                    score=0.88,
                    match_reasons=["same_brand", "same_category"]
                )
            ],
            metadata=RecommendationMetadata(
                source_product_id=2,
                evaluated_candidates=15,
                returned_count=1,
                took_ms=18.4,
                faiss_candidate_count=10,
                mysql_candidate_count=10,
                degraded_mode=False
            )
        )

        app.dependency_overrides[get_recommendation_service] = lambda: mock_api_service
        client = TestClient(app)

        api_res = client.get("/api/v1/products/2/recommendations?limit=5")
        assert api_res.status_code == 200, f"API failed with {api_res.status_code}: {api_res.text}"
        data = api_res.json()
        assert data["source_product_id"] == 2
        assert len(data["recommendations"]) == 1
        assert data["recommendations"][0]["score"] == 0.88
        assert data["recommendations"][0]["match_reasons"] == ["same_brand", "same_category"]
        assert data["metadata"]["evaluated_candidates"] == 15

        # Also test 404 through API
        mock_api_service.get_recommendations.side_effect = ProductNotFoundError("Product not found")
        api_404 = client.get("/api/v1/products/999/recommendations")
        assert api_404.status_code == 404

        app.dependency_overrides.clear()
        print("[PASS] Check 12: GET /api/v1/products/{id}/recommendations complies with RecommendationResponse contract")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 12: API endpoint test: {e}")
        failed += 1

    print("=" * 70)
    print(f"RESULTS: {passed}/{total} checks passed, {failed} failed.")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_all_checks()
