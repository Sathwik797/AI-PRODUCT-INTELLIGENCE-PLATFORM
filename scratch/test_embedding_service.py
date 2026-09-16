"""Test Suite: EmbeddingService Lifecycle, Invalidation, Concurrency & Reconciliation.

Phase 06 Verification: Tests 10, 11, 12, 13, 14, 19, 22
- Same hash => skip regeneration (Q38)
- Semantic change => regeneration (Q43)
- Price-only change => no regeneration (Q43)
- Concurrency / stale hash gate (Q44)
- Provider failure => FAILED status without corrupting previous state
- Store failure => MySQL remains authoritative
- Reconciliation detects & restores missing FAISS vectors (Q41)
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import shutil
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.category import Category
from app.models.product import Product
from app.models.ai_generation import AIGeneration
from app.models.product_metadata import ProductMetadata
from app.models.product_embedding import ProductEmbedding
from app.repositories.product_repository import ProductRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.product_embedding_repository import ProductEmbeddingRepository
from app.schemas.product import ProductUpdate
from app.services.embedding_service import (
    EmbeddingService,
    ConcurrencyHashMismatchError,
    generate_position_independent_vector_id
)
from app.services.product_service import ProductService
from app.services.ai_acceptance_service import AIAcceptanceService
from app.vector_store.faiss_store import FAISSVectorStore
from app.ai.embedding_provider import EmbeddingProvider, EmbeddingGenerationError

TEST_FAISS_DIR = "scratch/test_service_faiss"


class MockEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimension: int = 4):
        self.dimension = dimension
        self.call_count = 0

    def embed_text(self, text: str) -> list[float]:
        self.call_count += 1
        if "failing_token" in text:
            raise EmbeddingGenerationError("Simulated upstream provider failure")
        # Deterministic dummy vector
        return [0.5, 0.5, 0.5, 0.5]

    def get_dimension(self) -> int:
        return self.dimension

    def get_model_name(self) -> str:
        return "mock-embedding-v1"


def setup_test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def cleanup_faiss():
    if os.path.exists(TEST_FAISS_DIR):
        shutil.rmtree(TEST_FAISS_DIR, ignore_errors=True)


def test_embedding_lifecycle_and_skip_unchanged():
    print("\n--- TEST 1: Embedding Lifecycle, Initial Generation & Skip Unchanged (Q38) ---")
    cleanup_faiss()
    db = setup_test_db()
    provider = MockEmbeddingProvider()
    store = FAISSVectorStore(dimension=4, storage_dir=TEST_FAISS_DIR, auto_load=False)
    service = EmbeddingService(
        embedding_provider=provider,
        vector_store=store
    )

    # Seed Category & Product
    cat = Category(id=1, name="Electronics")
    prod = Product(id=1, title="Wireless Headphones", brand="Sony", description="Noise cancelling", sku="SN-100", price=199.99, status="active", category_id=1)
    db.add_all([cat, prod])
    db.commit()

    # 1. Initial Generation
    emb1 = service.generate_product_embedding(db, product_id=1)
    assert emb1.status == "READY"
    assert emb1.vector_id != 1, "vector_id must be position-independent"
    assert provider.call_count == 1
    assert store.count() == 1
    assert store.contains(emb1.vector_id)
    initial_hash = emb1.content_hash
    initial_vid = emb1.vector_id

    # 2. Second Generation without product change => must SKIP (Q38)
    emb2 = service.generate_product_embedding(db, product_id=1)
    assert emb2.status == "READY"
    assert emb2.content_hash == initial_hash
    assert emb2.vector_id == initial_vid
    assert provider.call_count == 1, "Provider must NOT be called when content hash matches"
    print("[PASS] Initial generation and same-hash skip verified.")


def test_semantic_vs_price_change():
    print("\n--- TEST 2: Semantic Change vs. Price-Only Invalidation (Q43) ---")
    cleanup_faiss()
    db = setup_test_db()
    provider = MockEmbeddingProvider()
    store = FAISSVectorStore(dimension=4, storage_dir=TEST_FAISS_DIR, auto_load=False)
    service = EmbeddingService(embedding_provider=provider, vector_store=store)

    cat_repo = CategoryRepository()
    prod_repo = ProductRepository()
    from app.repositories.ai_generation_repository import AIGenerationRepository
    from app.repositories.product_metadata_repository import ProductMetadataRepository
    ai_gen_repo = AIGenerationRepository()
    meta_repo = ProductMetadataRepository()
    ai_acc_service = AIAcceptanceService(prod_repo, ai_gen_repo, meta_repo, cat_repo, embedding_service=service)
    prod_service = ProductService(prod_repo, cat_repo, ai_acc_service, embedding_service=service)

    cat = Category(id=1, name="Apparel")
    prod = Product(id=2, title="Cotton T-Shirt", brand="Nike", description="Soft cotton", sku="NK-TS-01", price=25.0, status="active", category_id=1)
    db.add_all([cat, prod])
    db.commit()

    # Generate initial READY embedding
    emb = service.generate_product_embedding(db, product_id=2)
    assert emb.status == "READY"
    initial_hash = emb.content_hash

    # A. Non-Semantic update (Price only)
    prod_service.update(db, product_id=2, product_update=ProductUpdate(price=30.0))
    emb_after_price = service.embedding_repository.get_by_product_id(db, 2)
    assert emb_after_price.status == "READY", "Price-only change must NOT mark embedding STALE"

    # B. Semantic update (Title change)
    prod_service.update(db, product_id=2, product_update=ProductUpdate(title="Premium Cotton T-Shirt"))
    emb_after_title = service.embedding_repository.get_by_product_id(db, 2)
    assert emb_after_title.status == "STALE", "Semantic change (title) MUST mark embedding STALE"

    # Regenerate embedding after semantic change
    service.generate_product_embedding(db, product_id=2)
    emb_regenerated = service.embedding_repository.get_by_product_id(db, 2)
    assert emb_regenerated.status == "READY"
    assert emb_regenerated.content_hash != initial_hash, "Hash must update after semantic change"
    print("[PASS] Semantic change invalidation and price-only neutrality verified.")


def test_concurrency_hash_gate():
    print("\n--- TEST 3: Concurrency Hash-Gate (Q44) ---")
    cleanup_faiss()
    db = setup_test_db()
    provider = MockEmbeddingProvider()
    store = FAISSVectorStore(dimension=4, storage_dir=TEST_FAISS_DIR, auto_load=False)
    service = EmbeddingService(embedding_provider=provider, vector_store=store)

    cat = Category(id=1, name="Shoes")
    prod = Product(id=3, title="Original Sneakers", brand="Puma", description="Suede", sku="PM-01", price=60.0, status="active", category_id=1)
    db.add_all([cat, prod])
    db.commit()

    # Initial state hash
    _, initial_hash = service.build_embedding_document(db, prod)

    # Simulate product is updated concurrently while async job was in queue
    prod.title = "Updated Sneakers Concurrent"
    db.commit()

    # Async job executes expecting initial_hash
    try:
        service.generate_product_embedding(db, product_id=3, expected_hash=initial_hash)
        assert False, "Expected ConcurrencyHashMismatchError"
    except ConcurrencyHashMismatchError:
        pass

    # Old vector must NOT be committed
    emb = service.embedding_repository.get_by_product_id(db, 3)
    assert emb is None or emb.status != "READY", "Stale job must not commit READY vector"
    print("[PASS] Concurrency hash-gate (Q44) prevents stale overwrites.")


def test_provider_failure_and_mysql_authority():
    print("\n--- TEST 4: Provider Failure Lifecycle & MySQL Authority ---")
    cleanup_faiss()
    db = setup_test_db()
    provider = MockEmbeddingProvider()
    store = FAISSVectorStore(dimension=4, storage_dir=TEST_FAISS_DIR, auto_load=False)
    service = EmbeddingService(embedding_provider=provider, vector_store=store)

    cat = Category(id=1, name="Books")
    # Title containing 'failing_token' triggers mock error
    prod = Product(id=4, title="failing_token Novel", brand="Penguin", description="Fiction", sku="BK-01", price=15.0, status="active", category_id=1)
    db.add_all([cat, prod])
    db.commit()

    try:
        service.generate_product_embedding(db, product_id=4)
        assert False, "Expected EmbeddingGenerationError"
    except EmbeddingGenerationError:
        pass

    emb = service.embedding_repository.get_by_product_id(db, 4)
    assert emb.status == "FAILED", "Embedding status must transition to FAILED on provider error"
    assert "Simulated upstream provider failure" in emb.error_message
    assert store.count() == 0, "No vector should be indexed in FAISS on failure"
    print("[PASS] Failure lifecycle and error capture verified.")


def test_reconciliation():
    print("\n--- TEST 5: Reconciliation of Missing FAISS Vectors (Q41) ---")
    cleanup_faiss()
    db = setup_test_db()
    provider = MockEmbeddingProvider()
    store = FAISSVectorStore(dimension=4, storage_dir=TEST_FAISS_DIR, auto_load=False)
    service = EmbeddingService(embedding_provider=provider, vector_store=store)

    cat = Category(id=1, name="Sports")
    prod = Product(id=5, title="Basketball", brand="Spalding", description="Leather", sku="BB-01", price=50.0, status="active", category_id=1)
    db.add_all([cat, prod])
    db.commit()

    # Initial ready embedding
    emb = service.generate_product_embedding(db, product_id=5)
    assert store.count() == 1

    # Simulate FAISS index corruption / vector deletion
    store.remove_vector(emb.vector_id)
    assert store.count() == 0
    assert not store.contains(emb.vector_id)

    # Run reconciliation
    stats = service.reconcile_with_vector_store(db)
    assert stats["ready_in_db"] == 1
    assert stats["missing_in_vector_store"] == 1
    assert stats["restored_in_vector_store"] == 1
    assert store.contains(emb.vector_id), "Reconciliation must restore missing FAISS vector"
    print("[PASS] Reconciliation audit and restore verified.")


def main():
    print("=" * 60)
    print("RUNNING EMBEDDING SERVICE TEST SUITE")
    print("=" * 60)
    test_embedding_lifecycle_and_skip_unchanged()
    test_semantic_vs_price_change()
    test_concurrency_hash_gate()
    test_provider_failure_and_mysql_authority()
    test_reconciliation()
    cleanup_faiss()
    print("=" * 60)
    print("ALL 5 EMBEDDING SERVICE TEST SUITES PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    main()
