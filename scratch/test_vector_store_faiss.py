"""Test Suite: FAISSVectorStore Implementation.

Phase 06 Verification: Tests 17, 18, 20, 21
- FAISS IndexIDMap2 vector insertion
- Position-independent vector IDs (int64 != product_id)
- Normalization and cosine similarity
- Vector deletion and containment checks
- Atomic rebuild (Q49)
- Failed rebuild leaves active index untouched
- Atomic persistence and reload
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import shutil
import numpy as np
from app.vector_store.faiss_store import FAISSVectorStore
from app.vector_store.base import VectorStoreError

TEST_STORAGE_DIR = "scratch/test_faiss_data"


def cleanup():
    if os.path.exists(TEST_STORAGE_DIR):
        shutil.rmtree(TEST_STORAGE_DIR, ignore_errors=True)


def test_faiss_add_search_remove():
    print("\n--- TEST 1: FAISS Vector Insertion, Position-Independent IDs & Cosine Search ---")
    cleanup()
    store = FAISSVectorStore(dimension=4, storage_dir=TEST_STORAGE_DIR, auto_load=False)

    # Position-independent vector IDs (large 63-bit ints)
    vid1 = 9876543210123
    vid2 = 8765432109876

    vec1 = [1.0, 0.0, 0.0, 0.0]
    vec2 = [0.0, 1.0, 0.0, 0.0]

    store.add_vector(vid1, vec1)
    store.add_vector(vid2, vec2)

    assert store.count() == 2
    assert store.contains(vid1)
    assert store.contains(vid2)
    assert not store.contains(12345)

    # Search with identical vector to vec1 => similarity score ~ 1.0
    results = store.search([1.0, 0.0, 0.0, 0.0], top_k=2)
    assert len(results) == 2
    top_vid, top_score = results[0]
    assert top_vid == vid1
    assert abs(top_score - 1.0) < 1e-4

    # Search with orthognal query to vec1 => score ~ 0.0
    results_ortho = store.search([0.0, 1.0, 0.0, 0.0], top_k=1)
    assert results_ortho[0][0] == vid2

    # Remove vector
    store.remove_vector(vid1)
    assert store.count() == 1
    assert not store.contains(vid1)
    assert store.contains(vid2)

    cleanup()
    print("[PASS] Vector add, position-independent IDs, cosine search, and remove verified.")


def test_faiss_persistence_and_reload():
    print("\n--- TEST 2: FAISS Atomic File Persistence and Reload ---")
    cleanup()
    store = FAISSVectorStore(dimension=4, storage_dir=TEST_STORAGE_DIR, auto_load=False)

    vid = 555000111222
    store.add_vector(vid, [0.5, 0.5, 0.5, 0.5])
    assert store.count() == 1

    # Reload in a separate instance
    store2 = FAISSVectorStore(dimension=4, storage_dir=TEST_STORAGE_DIR, auto_load=True)
    assert store2.count() == 1
    assert store2.contains(vid)

    cleanup()
    print("[PASS] Index persistence and reload verified.")


def test_faiss_atomic_rebuild_and_failure_isolation():
    print("\n--- TEST 3: Atomic Rebuild & Failed Rebuild Isolation (Q49) ---")
    cleanup()
    store = FAISSVectorStore(dimension=4, storage_dir=TEST_STORAGE_DIR, auto_load=False)

    # Initial active index state
    initial_vid = 111111111111
    store.add_vector(initial_vid, [1.0, 0.0, 0.0, 0.0])
    assert store.count() == 1

    # Successful rebuild
    new_vectors = [
        (222222222222, [0.0, 1.0, 0.0, 0.0]),
        (333333333333, [0.0, 0.0, 1.0, 0.0])
    ]
    store.rebuild(new_vectors)
    assert store.count() == 2
    assert not store.contains(initial_vid), "Old vectors should be replaced by rebuilt set"
    assert store.contains(222222222222)
    assert store.contains(333333333333)

    # Failed rebuild attempt (dimension mismatch in vector)
    bad_vectors = [
        (444444444444, [1.0, 0.0])  # Only 2 dimensions instead of 4
    ]
    try:
        store.rebuild(bad_vectors)
        assert False, "Expected VectorStoreError on dimension mismatch"
    except VectorStoreError as e:
        assert "dimension mismatch" in str(e).lower()

    # Active index MUST remain completely intact after failure!
    assert store.count() == 2, "Active index count must remain unchanged after failed rebuild"
    assert store.contains(222222222222)
    assert store.contains(333333333333)

    cleanup()
    print("[PASS] Atomic rebuild and failed rebuild isolation (Q49) verified.")


def main():
    print("=" * 60)
    print("RUNNING FAISS VECTOR STORE TEST SUITE")
    print("=" * 60)
    test_faiss_add_search_remove()
    test_faiss_persistence_and_reload()
    test_faiss_atomic_rebuild_and_failure_isolation()
    print("=" * 60)
    print("ALL 3 FAISS VECTOR STORE TEST SUITES PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    main()
