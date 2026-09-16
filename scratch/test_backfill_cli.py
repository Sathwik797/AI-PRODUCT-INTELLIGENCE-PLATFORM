"""Test Suite: Backfill Embeddings CLI.

Phase 06 Verification: Tests 23, 24, 25
- Explicit backfill command execution
- Same-hash skip behavior (Q53)
- Fault isolation: single product failure does not halt process
- Safe retry capability
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import shutil
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.category import Category
from app.models.product import Product
from app.commands.backfill_embeddings import run_backfill
from app.services.embedding_service import EmbeddingService
from app.vector_store.faiss_store import FAISSVectorStore
from app.ai.embedding_provider import EmbeddingProvider, EmbeddingGenerationError

TEST_CLI_FAISS_DIR = "scratch/test_cli_faiss"


class MockBackfillProvider(EmbeddingProvider):
    def __init__(self, dimension: int = 4):
        self.dimension = dimension
        self.generated_count = 0

    def embed_text(self, text: str) -> list[float]:
        self.generated_count += 1
        if "bad_item" in text.lower():
            raise EmbeddingGenerationError("Simulated item defect")
        return [0.1, 0.2, 0.3, 0.4]

    def get_dimension(self) -> int:
        return self.dimension

    def get_model_name(self) -> str:
        return "mock-backfill-v1"


def cleanup():
    if os.path.exists(TEST_CLI_FAISS_DIR):
        shutil.rmtree(TEST_CLI_FAISS_DIR, ignore_errors=True)


def test_backfill_execution_and_skip():
    print("\n--- TEST: Backfill CLI Execution, Skip Unchanged & Error Tolerance ---")
    cleanup()

    from sqlalchemy.pool import StaticPool
    # Setup isolated test database with StaticPool
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()

    cat = Category(id=1, name="General")
    p1 = Product(id=1, title="Item 1", brand="A", sku="S1", price=10.0, status="active", category_id=1)
    p2 = Product(id=2, title="Item 2 bad_item", brand="B", sku="S2", price=20.0, status="active", category_id=1)
    p3 = Product(id=3, title="Item 3", brand="C", sku="S3", price=30.0, status="active", category_id=1)
    db.add_all([cat, p1, p2, p3])
    db.commit()

    provider = MockBackfillProvider()
    store = FAISSVectorStore(dimension=4, storage_dir=TEST_CLI_FAISS_DIR, auto_load=False)
    service = EmbeddingService(embedding_provider=provider, vector_store=store)

    # Monkeypatch SessionLocal in backfill command to use our test DB session factory
    from unittest.mock import patch
    with patch("app.commands.backfill_embeddings.SessionLocal", new=TestingSessionLocal):
        # 1. First run: p1, p3 succeed; p2 fails
        summary1 = run_backfill(force=False, service=service)
        assert summary1["total"] == 3
        assert summary1["generated"] == 2
        assert summary1["skipped"] == 0
        assert summary1["failed"] == 1
        assert store.count() == 2

        # 2. Second run (Retry without change): p1, p3 skipped; p2 fails again
        summary2 = run_backfill(force=False, service=service)
        assert summary2["total"] == 3
        assert summary2["generated"] == 0, "No unchanged items should be regenerated"
        assert summary2["skipped"] == 2, "Unchanged items must be skipped"
        assert summary2["failed"] == 1

        # 3. Fix p2 and retry
        p2.title = "Item 2 Fixed"
        db.commit()

        summary3 = run_backfill(force=False, service=service)
        assert summary3["total"] == 3
        assert summary3["generated"] == 1, "Only fixed item should be generated"
        assert summary3["skipped"] == 2
        assert summary3["failed"] == 0
        assert store.count() == 3

    cleanup()
    print("[PASS] Backfill CLI execution, skip unchanged, error isolation, and retry verified.")


if __name__ == "__main__":
    test_backfill_execution_and_skip()
