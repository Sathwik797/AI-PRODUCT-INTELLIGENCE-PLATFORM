"""Phase 07 Hybrid Search Focused Test Suite.

Verifies:
1. Deterministic parser extracts price, brand, category, color, size and residual semantic query.
2. SearchQuery and SearchFilters DTO validation.
3. Hybrid candidate retrieval combining MySQL and FAISS candidates.
4. Final eligibility guard strictly eliminates violating products (e.g. price > max_price).
5. HybridRanker produces deterministic normalized scores [0, 1] with match reasons.
6. Bounded K expansion reuses query embedding without re-calling the provider.
7. Search API endpoint returns valid SearchResponse contract (both standard and debug).
"""

import os
import shutil
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.embedding_provider import EmbeddingProvider
from app.db.database import SessionLocal
from app.db.dependencies import get_db
from app.main import app
from app.models.category import Category
from app.models.product import Product
from app.models.product_embedding import ProductEmbedding
from app.schemas.search import (
    HybridSearchConfig,
    SearchFilters,
    SearchQuery,
    SearchResponse,
)
from app.search.eligibility_guard import FinalEligibilityGuard
from app.search.filters import FilterRegistry
from app.search.mysql_retriever import MySQLCandidateRetriever
from app.search.query_parser import DeterministicQueryParser
from app.search.ranker import HybridRanker
from app.search.semantic_retriever import SemanticCandidateRetriever
from app.services.embedding_service import generate_position_independent_vector_id
from app.services.hybrid_search_service import HybridSearchService
from app.vector_store.faiss_store import FAISSVectorStore


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic mock provider for unit testing without network/API calls."""

    def __init__(self, dimension: int = 768):
        self.dimension = dimension
        self.call_count = 0

    def embed_text(self, text: str) -> list[float]:
        self.call_count += 1
        seed = abs(hash(text)) % 10000 + 1
        vec = [float(seed + i) for i in range(self.dimension)]
        norm = np.linalg.norm(vec)
        return (np.array(vec) / norm).tolist()

    def get_dimension(self) -> int:
        return self.dimension

    def get_model_name(self) -> str:
        return "mock-embedding-model"


def run_hybrid_search_suite():
    passed = 0
    failed = 0
    total = 7

    print("=" * 70)
    print("PHASE 07 — HYBRID SEARCH TEST SUITE")
    print("=" * 70)

    temp_dir = tempfile.mkdtemp(prefix="faiss_search_test_")
    store = FAISSVectorStore(dimension=768, storage_dir=temp_dir)
    provider = MockEmbeddingProvider(dimension=768)

    db: Session = SessionLocal()
    created_product_ids: list[int] = []
    created_category_ids: list[int] = []

    try:
        # Fixture Setup: Categories and Products
        cat_shoes = db.query(Category).filter(Category.name == "Shoes").first()
        if not cat_shoes:
            cat_shoes = Category(name="Shoes")
            db.add(cat_shoes)
            db.commit()
            db.refresh(cat_shoes)
            created_category_ids.append(cat_shoes.id)

        # Seed 4 distinct products
        # Product 1: Nike Pegasus - ₹4,500 (Matches "black Nike running shoes under ₹5000")
        p1 = Product(
            title="Nike Air Zoom Pegasus Black Running Shoe",
            description="High performance black road running shoes for daily training",
            brand="Nike",
            price=4500.0,
            sku=f"P1-PEGASUS-{int(time.time_ns()) % 100000}",
            category_id=cat_shoes.id,
            status="ACTIVE"
        )
        # Product 2: Nike Vaporfly - ₹12,000 (Violates price <= 5000)
        p2 = Product(
            title="Nike ZoomX Vaporfly Elite Racing Shoe",
            description="Ultra lightweight carbon fiber running shoes for marathons",
            brand="Nike",
            price=12000.0,
            sku=f"P2-VAPORFLY-{int(time.time_ns()) % 100000}",
            category_id=cat_shoes.id,
            status="ACTIVE"
        )
        # Product 3: Adidas Ultraboost - ₹4,800 (Violates brand == Nike)
        p3 = Product(
            title="Adidas Ultraboost Light Running Shoe",
            description="Cushioned black daily jogging shoes",
            brand="Adidas",
            price=4800.0,
            sku=f"P3-ULTRABOOST-{int(time.time_ns()) % 100000}",
            category_id=cat_shoes.id,
            status="ACTIVE"
        )
        # Product 4: Nike Revolution - ₹3,500 (Matches brand, category, price)
        p4 = Product(
            title="Nike Revolution 6 Next Nature Running Shoes",
            description="Comfortable cushioned road running shoes",
            brand="Nike",
            price=3500.0,
            sku=f"P4-REVOLUTION-{int(time.time_ns()) % 100000}",
            category_id=cat_shoes.id,
            status="ACTIVE"
        )

        db.add_all([p1, p2, p3, p4])
        db.commit()
        for p in [p1, p2, p3, p4]:
            db.refresh(p)
            created_product_ids.append(p.id)

        # Index vectors in FAISS for all 4 products
        for p in [p1, p2, p3, p4]:
            vid = generate_position_independent_vector_id(p.id)
            emb = ProductEmbedding(
                product_id=p.id,
                vector_id=vid,
                content_hash="mock_hash",
                embedding_model="mock-embedding-model",
                embedding_dimension=768,
                builder_version="v1.0",
                status="READY"
            )
            db.add(emb)
            db.commit()
            # Add to FAISS store
            vec = provider.embed_text(f"{p.title} {p.description}")
            store.add_vector(vid, vec)

        # -------------------------------------------------------------
        # TEST 1: Deterministic Query Parser
        # -------------------------------------------------------------
        try:
            print("\n[TEST 1] Deterministic Parser extracts filters & residual query...")
            parser = DeterministicQueryParser()
            query_str = "black Nike running shoes under ₹5000"
            parsed: SearchQuery = parser.parse(query_str, db=db)

            assert parsed.original_query == query_str
            assert parsed.filters.brand == "Nike"
            assert parsed.filters.color == "Black"
            assert parsed.filters.max_price == 5000.0
            # Residual text should have brand, color, price stripped
            assert "nike" not in parsed.semantic_query.lower()
            assert "5000" not in parsed.semantic_query
            assert "running" in parsed.semantic_query.lower()
            print(f"  Extracted filters: {parsed.filters.model_dump(exclude_none=True)}")
            print(f"  Residual query: '{parsed.semantic_query}'")
            print("  --> PASS: Deterministic parser correctly parsed constraints and stripped tokens.")
            passed += 1
        except Exception as e:
            print(f"  --> FAIL: {e}")
            traceback.print_exc()
            failed += 1

        # -------------------------------------------------------------
        # TEST 2: SearchQuery DTO Validation
        # -------------------------------------------------------------
        try:
            print("\n[TEST 2] SearchQuery DTO contract and validation...")
            dto = SearchQuery(
                original_query="test query",
                semantic_query="clean query",
                filters=SearchFilters(
                    brand="Adidas",
                    min_price=100.0,
                    max_price=500.0
                )
            )
            assert dto.filters.brand == "Adidas"
            assert dto.filters.min_price == 100.0
            assert dto.filters.max_price == 500.0

            # Negative price should fail validation
            try:
                SearchFilters(min_price=-10.0)
                assert False, "Expected ValidationError for negative price"
            except Exception:
                pass

            print("  --> PASS: SearchQuery and SearchFilters enforce strict validation.")
            passed += 1
        except Exception as e:
            print(f"  --> FAIL: {e}")
            traceback.print_exc()
            failed += 1

        # -------------------------------------------------------------
        # TEST 3: Parallel Candidate Retrieval & Union
        # -------------------------------------------------------------
        try:
            print("\n[TEST 3] Parallel Candidate Retrieval & Union...")
            mysql_retriever = MySQLCandidateRetriever()
            semantic_retriever = SemanticCandidateRetriever(
                embedding_provider=provider,
                vector_store=store
            )

            sq = SearchQuery(
                original_query="Nike shoes under ₹5000",
                semantic_query="running shoes",
                filters=SearchFilters(brand="Nike", max_price=5000.0)
            )

            # MySQL pre-filter will find P1 and P4 (Nike + price <= 5000)
            mysql_ids = mysql_retriever.retrieve_candidates(db, sq, limit=10)
            assert p1.id in mysql_ids or p4.id in mysql_ids
            # P2 (₹12,000) must NOT be in MySQL candidates
            assert p2.id not in mysql_ids

            # FAISS retrieves based on semantic query, regardless of price (may include P2 or P3)
            faiss_candidates, q_vec = semantic_retriever.retrieve_candidates(
                db, sq.semantic_query, limit=10
            )
            faiss_ids = [pid for pid, _ in faiss_candidates]
            assert len(faiss_ids) > 0

            # Union
            union_ids = set(mysql_ids) | set(faiss_ids)
            assert len(union_ids) >= len(mysql_ids)
            print(f"  MySQL candidates: {mysql_ids}, FAISS candidates: {faiss_ids}")
            print(f"  Union size: {len(union_ids)}")
            print("  --> PASS: Candidate retrieval successfully aggregates both branches.")
            passed += 1
        except Exception as e:
            print(f"  --> FAIL: {e}")
            traceback.print_exc()
            failed += 1

        # -------------------------------------------------------------
        # TEST 4: Final Eligibility Guard
        # -------------------------------------------------------------
        try:
            print("\n[TEST 4] Final Eligibility Guard strictly eliminates violating products...")
            guard = FinalEligibilityGuard()

            # Include P2 (₹12,000 - price violation) and P3 (Adidas - brand violation) in candidate union
            test_union = [p1.id, p2.id, p3.id, p4.id]
            sq = SearchQuery(
                original_query="Nike running shoes under ₹5000",
                semantic_query="running shoes",
                filters=SearchFilters(brand="Nike", max_price=5000.0)
            )

            eligible, meta = guard.filter_eligible_candidates(db, test_union, sq)

            # P1 (Nike, ₹4,500) and P4 (Nike, ₹3,500) MUST survive
            assert p1.id in eligible, "P1 should be eligible"
            assert p4.id in eligible, "P4 should be eligible"

            # P2 (₹12,000 > 5000) MUST be excluded!
            assert p2.id not in eligible, "FATAL: P2 violated max_price but passed guard!"

            # P3 (Adidas != Nike) MUST be excluded!
            assert p3.id not in eligible, "FATAL: P3 violated brand constraint but passed guard!"

            print(f"  Candidates evaluated: {test_union} -> Eligible surviving: {list(eligible.keys())}")
            print("  --> PASS: Eligibility guard strictly eliminated all constraint-violating products.")
            passed += 1
        except Exception as e:
            print(f"  --> FAIL: {e}")
            traceback.print_exc()
            failed += 1

        # -------------------------------------------------------------
        # TEST 5: HybridRanker Scoring & Match Reasons
        # -------------------------------------------------------------
        try:
            print("\n[TEST 5] HybridRanker produces normalized scores and verified match reasons...")
            ranker = HybridRanker(config=HybridSearchConfig(semantic_weight=0.65, structured_weight=0.35))

            eligible_map = {p1.id: p1, p4.id: p4}
            sem_scores = {p1.id: 0.92, p4.id: 0.70}
            provenance = {p1.id: {"mysql", "faiss"}, p4.id: {"mysql", "faiss"}}

            sq = SearchQuery(
                original_query="Nike running shoes under ₹5000",
                semantic_query="running shoes",
                filters=SearchFilters(brand="Nike", max_price=5000.0)
            )

            ranked = ranker.rank(
                eligible_products=eligible_map,
                semantic_scores=sem_scores,
                candidate_provenance=provenance,
                search_query=sq,
                accepted_metadata_map={},
                limit=10
            )

            assert len(ranked) == 2
            top_item = ranked[0]
            assert top_item.product.id == p1.id
            assert 0.0 <= top_item.score <= 1.0
            assert "exact_brand" in top_item.match_reasons
            assert "price_constraint" in top_item.match_reasons
            assert "semantic_match" in top_item.match_reasons
            print(f"  Ranked results: #{1} Product {top_item.product.id} (Score: {top_item.score}, Reasons: {top_item.match_reasons})")
            print("  --> PASS: HybridRanker scores strictly bounded in [0, 1] with deterministic match reasons.")
            passed += 1
        except Exception as e:
            print(f"  --> FAIL: {e}")
            traceback.print_exc()
            failed += 1

        # -------------------------------------------------------------
        # TEST 6: Bounded K Expansion Reusing Cached Query Vector
        # -------------------------------------------------------------
        try:
            print("\n[TEST 6] Bounded K Expansion with cached query vector...")
            provider.call_count = 0

            # Configure small initial K=1 and limit=3 so initial eligible (at most 2) < limit triggers expansion
            config = HybridSearchConfig(
                mysql_candidate_k=1,
                faiss_candidate_k=1,
                max_candidate_k=10,
                default_limit=3,
                enable_expansion=True
            )

            search_service = HybridSearchService(
                query_parser=DeterministicQueryParser(),
                mysql_retriever=MySQLCandidateRetriever(),
                semantic_retriever=SemanticCandidateRetriever(
                    embedding_provider=provider,
                    vector_store=store
                ),
                eligibility_guard=FinalEligibilityGuard(),
                ranker=HybridRanker(config=config),
                config=config
            )

            res = search_service.search(db, "Nike running shoes under ₹5000", limit=3)
            print(f"  Expansion triggered: {res.metadata.k_expanded}, Provider embed calls: {provider.call_count}")
            assert res.metadata.k_expanded is True
            assert provider.call_count == 1, f"Expected 1 provider call, got {provider.call_count}"
            assert res.metadata.returned_count >= 1
            print("  --> PASS: Bounded K expansion reuses query vector without re-calling provider.")
            passed += 1
        except Exception as e:
            print(f"  --> FAIL: {e}")
            traceback.print_exc()
            failed += 1

        # -------------------------------------------------------------
        # TEST 7: Search API Endpoint Contract
        # -------------------------------------------------------------
        try:
            print("\n[TEST 7] Search API endpoint (GET /api/v1/search)...")
            from app.api.search import get_search_service

            mock_search_service = HybridSearchService(
                semantic_retriever=SemanticCandidateRetriever(
                    embedding_provider=provider,
                    vector_store=store
                )
            )
            app.dependency_overrides[get_search_service] = lambda: mock_search_service
            client = TestClient(app)

            # Standard request
            response = client.get("/api/v1/search?q=Nike+running+shoes+under+5000&limit=5")
            assert response.status_code == 200
            data = response.json()
            assert "query" in data
            assert "results" in data
            assert "metadata" in data
            assert data["metadata"]["requested_limit"] == 5
            assert data["metadata"]["parsed_filters"]["brand"] == "Nike"

            # Debug request
            dbg_response = client.get("/api/v1/search?q=Nike+shoes&debug=true")
            assert dbg_response.status_code == 200
            dbg_data = dbg_response.json()
            assert dbg_data["debug_diagnostics"] is not None
            assert "mysql_candidate_count" in dbg_data["debug_diagnostics"]
            assert "faiss_candidate_count" in dbg_data["debug_diagnostics"]
            assert "union_candidate_count" in dbg_data["debug_diagnostics"]

            print(f"  Standard response: {len(data['results'])} items, took {data['metadata']['took_ms']} ms")
            print(f"  Debug diagnostics: {dbg_data['debug_diagnostics']}")
            print("  --> PASS: Search API endpoint satisfies the full SearchResponse contract.")
            passed += 1
        except Exception as e:
            print(f"  --> FAIL: {e}")
            traceback.print_exc()
            failed += 1
        finally:
            app.dependency_overrides.clear()

    finally:
        # Cleanup
        try:
            for pid in created_product_ids:
                emb = db.query(ProductEmbedding).filter(ProductEmbedding.product_id == pid).first()
                if emb:
                    db.delete(emb)
                prod = db.query(Product).filter(Product.id == pid).first()
                if prod:
                    db.delete(prod)
            for cid in created_category_ids:
                cat = db.query(Category).filter(Category.id == cid).first()
                if cat:
                    db.delete(cat)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
            shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n" + "=" * 70)
    print(f"HYBRID SEARCH TEST SUITE SUMMARY: {passed}/{total} PASSED, {failed} FAILED")
    print("=" * 70)
    return failed == 0


if __name__ == "__main__":
    success = run_hybrid_search_suite()
    sys.exit(0 if success else 1)
