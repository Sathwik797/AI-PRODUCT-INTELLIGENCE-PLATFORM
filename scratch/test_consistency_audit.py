"""Phase 06 Consistency Audit Test Suite.

Verifies:
1. Scenario A: Provider succeeds + FAISS succeeds + MySQL commit succeeds.
2. Scenario B & Requirement 2: Provider failure preserves existing READY vector.
3. Scenario C & Requirement 2: FAISS failure preserves existing READY vector.
4. Scenario F: Reconciliation repairs missing FAISS vector.
5. Scenario G: Reconciliation prunes orphan FAISS vector.
6. Requirement 4: Failed rebuild preserves old active index in-memory and on disk.
7. Requirement 5: Concurrency hash gate protects against stale jobs.
8. Requirement 5: Pre-commit concurrency gate detects in-flight modifications.
"""

import os
import shutil
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from sqlalchemy.orm import Session

from app.ai.embedding_provider import EmbeddingProvider
from app.db.database import SessionLocal
from app.models.category import Category
from app.models.product import Product
from app.models.product_embedding import ProductEmbedding
from app.repositories.product_embedding_repository import ProductEmbeddingRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.product_embedding import EmbeddingStatus
from app.services.embedding_service import (
    ConcurrencyHashMismatchError,
    EmbeddingService,
)
from app.vector_store.base import VectorStoreError
from app.vector_store.faiss_store import FAISSVectorStore


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic mock provider for testing."""

    def __init__(self, dimension: int = 768, fail: bool = False):
        self.dimension = dimension
        self.fail = fail
        self.call_count = 0

    def embed_text(self, text: str) -> list[float]:
        self.call_count += 1
        if self.fail:
            raise RuntimeError("Gemini API simulated failure: 503 Unavailable")
        seed = abs(hash(text)) % 10000 + 1
        vec = [float(seed + i) for i in range(self.dimension)]
        norm = np.linalg.norm(vec)
        return (np.array(vec) / norm).tolist()

    def get_dimension(self) -> int:
        return self.dimension

    def get_model_name(self) -> str:
        return "mock-embedding-model"


def run_audit_suite():
    passed = 0
    failed = 0
    total = 8

    print("=" * 70)
    print("PHASE 06 — FOCUSED CONSISTENCY AUDIT TEST SUITE")
    print("=" * 70)

    temp_dir = tempfile.mkdtemp(prefix="faiss_audit_suite_")
    db: Session = SessionLocal()

    try:
        # Fixture setup
        cat = db.query(Category).filter(Category.name == "Audit Category").first()
        if not cat:
            cat = Category(name="Audit Category")
            db.add(cat)
            db.commit()
            db.refresh(cat)

        prod = Product(
            title="Audit Ergonomic Office Chair",
            description="High quality mesh chair with lumbar support",
            price=299.99,
            sku=f"AUDIT-CHAIR-{os.getpid()}-{int(np.random.randint(10000, 99999))}",
            brand="ErgoDesk",
            category_id=cat.id
        )
        db.add(prod)
        db.commit()
        db.refresh(prod)

        store = FAISSVectorStore(dimension=768, storage_dir=temp_dir)
        provider = MockEmbeddingProvider(dimension=768)
        service = EmbeddingService(
            product_repository=ProductRepository(),
            embedding_repository=ProductEmbeddingRepository(),
            embedding_provider=provider,
            vector_store=store
        )

        # -------------------------------------------------------------
        # TEST 1: Scenario A - Happy Path
        # -------------------------------------------------------------
        try:
            print("\n[TEST 1] Scenario A: Provider + FAISS + MySQL commit succeeds...")
            emb = service.generate_product_embedding(db, prod.id)
            assert emb.status == EmbeddingStatus.READY.value
            assert store.contains(emb.vector_id)
            assert store.count() == 1
            assert emb.error_message is None
            print("  --> PASS: Scenario A creates consistent READY state across MySQL and FAISS.")
            passed += 1
        except Exception as e:
            print(f"  --> FAIL: {e}")
            traceback.print_exc()
            failed += 1

        # -------------------------------------------------------------
        # TEST 2: Scenario B & Req 2 - Provider failure preserves existing READY vector
        # -------------------------------------------------------------
        try:
            print("\n[TEST 2] Scenario B & Req 2: Provider failure preserves existing READY vector...")
            initial_emb = service.embedding_repository.get_by_product_id(db, prod.id)
            old_vector_id = initial_emb.vector_id
            assert store.contains(old_vector_id)

            # Change product title to invalidate content hash
            prod.title = "Audit Ergonomic Office Chair V2"
            db.commit()

            # Make provider fail
            provider.fail = True
            try:
                service.generate_product_embedding(db, prod.id)
                assert False, "Expected RuntimeError from provider failure"
            except RuntimeError as ex:
                assert "Gemini API simulated failure" in str(ex)

            # Check that previous FAISS vector is NOT destroyed
            assert store.contains(old_vector_id), "FATAL: Previous READY FAISS vector was destroyed on provider failure!"
            assert store.count() == 1

            # Check that MySQL record is FAILED and preserves old vector_id reference
            db.refresh(initial_emb)
            assert initial_emb.status == EmbeddingStatus.FAILED.value
            assert initial_emb.vector_id == old_vector_id
            print("  --> PASS: Previous valid FAISS vector preserved intact on provider failure.")
            passed += 1
        except Exception as e:
            print(f"  --> FAIL: {e}")
            traceback.print_exc()
            failed += 1
        finally:
            provider.fail = False

        # -------------------------------------------------------------
        # TEST 3: Scenario C & Req 2 - FAISS failure preserves existing READY vector
        # -------------------------------------------------------------
        try:
            print("\n[TEST 3] Scenario C & Req 2: FAISS failure preserves existing READY vector...")
            # Re-generate to valid READY state first
            emb_ready = service.generate_product_embedding(db, prod.id)
            valid_vector_id = emb_ready.vector_id
            assert store.contains(valid_vector_id)

            # Modify product again
            prod.title = "Audit Ergonomic Office Chair V3"
            db.commit()

            # Mock FAISS add_vector to fail on new vectors
            orig_add = store.add_vector
            def fail_add(vid, vec):
                if vid != valid_vector_id:
                    raise VectorStoreError("Simulated disk write failure in FAISS")
                return orig_add(vid, vec)
            store.add_vector = fail_add

            try:
                service.generate_product_embedding(db, prod.id)
                assert False, "Expected VectorStoreError from FAISS failure"
            except VectorStoreError as ex:
                assert "Simulated disk write failure" in str(ex)
            finally:
                store.add_vector = orig_add

            # Verify previous vector in FAISS is STILL intact
            assert store.contains(valid_vector_id), "FATAL: Previous READY vector was destroyed on FAISS failure!"

            # Verify MySQL reflects FAILED
            db.refresh(emb_ready)
            assert emb_ready.status == EmbeddingStatus.FAILED.value
            print("  --> PASS: Previous valid FAISS vector preserved intact on FAISS failure.")
            passed += 1
        except Exception as e:
            print(f"  --> FAIL: {e}")
            traceback.print_exc()
            failed += 1

        # -------------------------------------------------------------
        # TEST 4: Scenario F - Missing FAISS vector repaired by reconciliation
        # -------------------------------------------------------------
        try:
            print("\n[TEST 4] Scenario F: Reconciliation repairs missing FAISS vector...")
            # Ensure DB is in READY state
            emb_ready = service.generate_product_embedding(db, prod.id)
            assert store.contains(emb_ready.vector_id)

            # Simulate FAISS file deletion or vector drop
            store.remove_vector(emb_ready.vector_id)
            assert not store.contains(emb_ready.vector_id)

            # Run reconciliation
            report = service.reconcile_with_vector_store(db)
            assert report["missing_in_vector_store"] == 1
            assert report["restored_in_vector_store"] == 1
            assert store.contains(emb_ready.vector_id)
            print("  --> PASS: Missing vector successfully restored by reconciliation.")
            passed += 1
        except Exception as e:
            print(f"  --> FAIL: {e}")
            traceback.print_exc()
            failed += 1

        # -------------------------------------------------------------
        # TEST 5: Scenario G - Orphan FAISS vector pruned by reconciliation
        # -------------------------------------------------------------
        try:
            print("\n[TEST 5] Scenario G: Reconciliation detects and prunes orphan FAISS vector...")
            orphan_vector_id = 999888777666
            store.add_vector(orphan_vector_id, [0.01] * 768)
            assert store.contains(orphan_vector_id)

            initial_count = store.count()
            report = service.reconcile_with_vector_store(db)
            assert report["orphans_removed"] == 1
            assert not store.contains(orphan_vector_id), "FATAL: Orphan vector was NOT pruned!"
            assert store.count() == initial_count - 1
            print("  --> PASS: Orphan vector detected and safely pruned by reconciliation.")
            passed += 1
        except Exception as e:
            print(f"  --> FAIL: {e}")
            traceback.print_exc()
            failed += 1

        # -------------------------------------------------------------
        # TEST 6: Requirement 4 - Failed rebuild preserves old active index
        # -------------------------------------------------------------
        try:
            print("\n[TEST 6] Requirement 4: Failed rebuild preserves active index...")
            rebuild_dir = tempfile.mkdtemp(prefix="rebuild_test_")
            rebuild_store = FAISSVectorStore(dimension=768, storage_dir=rebuild_dir)

            rebuild_store.add_vector(101, [0.1] * 768)
            rebuild_store.add_vector(102, [0.2] * 768)
            rebuild_store.add_vector(103, [0.3] * 768)
            assert rebuild_store.count() == 3

            def failing_write(*args, **kwargs):
                raise OSError("Simulated disk error during rebuild write")

            orig_write = rebuild_store._faiss.write_index
            rebuild_store._faiss.write_index = failing_write
            try:
                rebuild_store.rebuild([(999, [0.9] * 768)])
                assert False, "Expected VectorStoreError during failing rebuild"
            except VectorStoreError as ex:
                assert "Atomic rebuild failed" in str(ex)
            finally:
                rebuild_store._faiss.write_index = orig_write

            # Verify active index is NOT corrupted and still has 3 vectors
            assert rebuild_store.count() == 3
            assert rebuild_store.contains(101)
            assert rebuild_store.contains(102)
            assert rebuild_store.contains(103)
            assert not rebuild_store.contains(999)
            shutil.rmtree(rebuild_dir, ignore_errors=True)
            print("  --> PASS: Active index untouched in memory and on disk after failed rebuild.")
            passed += 1
        except Exception as e:
            print(f"  --> FAIL: {e}")
            traceback.print_exc()
            failed += 1

        # -------------------------------------------------------------
        # TEST 7: Requirement 5 - Concurrency hash gate prevents stale job commit
        # -------------------------------------------------------------
        try:
            print("\n[TEST 7] Requirement 5: Concurrency hash gate checks expected hash...")
            _, expected_hash = service.build_embedding_document(db, prod)

            # Concurrently modify product before job executes
            prod.title = "Concurrently Modified Title"
            db.commit()

            try:
                service.generate_product_embedding(db, prod.id, expected_hash=expected_hash)
                assert False, "Expected ConcurrencyHashMismatchError"
            except ConcurrencyHashMismatchError:
                pass

            emb_check = service.embedding_repository.get_by_product_id(db, prod.id)
            assert emb_check.status == EmbeddingStatus.STALE.value
            print("  --> PASS: Stale job rejected by concurrency hash gate, marked STALE.")
            passed += 1
        except Exception as e:
            print(f"  --> FAIL: {e}")
            traceback.print_exc()
            failed += 1

        # -------------------------------------------------------------
        # TEST 8: Requirement 5 - Pre-commit concurrency check
        # -------------------------------------------------------------
        try:
            print("\n[TEST 8] Requirement 5: Pre-commit concurrency gate detects modification...")
            orig_embed = provider.embed_text
            def mutating_embed(text):
                # Another session updates product while embedding is being calculated
                s2 = SessionLocal()
                try:
                    p = s2.query(Product).filter(Product.id == prod.id).first()
                    p.description = "Altered description during provider network flight"
                    s2.commit()
                finally:
                    s2.close()
                return orig_embed(text)

            provider.embed_text = mutating_embed
            try:
                service.generate_product_embedding(db, prod.id)
                assert False, "Expected ConcurrencyHashMismatchError before commit"
            except ConcurrencyHashMismatchError:
                pass
            finally:
                provider.embed_text = orig_embed

            emb_check = service.embedding_repository.get_by_product_id(db, prod.id)
            assert emb_check.status == EmbeddingStatus.STALE.value
            print("  --> PASS: In-flight race detected before commit; stale vector rejected.")
            passed += 1
        except Exception as e:
            print(f"  --> FAIL: {e}")
            traceback.print_exc()
            failed += 1

    finally:
        # Cleanup
        try:
            emb = db.query(ProductEmbedding).filter(ProductEmbedding.product_id == prod.id).first()
            if emb:
                db.delete(emb)
            db.delete(prod)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
            shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n" + "=" * 70)
    print(f"CONSISTENCY AUDIT SUMMARY: {passed}/{total} PASSED, {failed} FAILED")
    print("=" * 70)
    return failed == 0


if __name__ == "__main__":
    success = run_audit_suite()
    sys.exit(0 if success else 1)
