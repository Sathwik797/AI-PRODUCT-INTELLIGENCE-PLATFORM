"""Test Suite: Alembic Product Embeddings Migration Up/Down.

Phase 06 Verification: Tests 26, 27
- Verifies upgrade from Phase 01-05 baseline to Phase 06 (70f0c7f28370)
- Verifies downgrade back to baseline, removing product_embeddings while preserving Phase 01-05 tables.
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect

TEST_DB_PATH = "scratch/test_emb_migration.db"


def cleanup():
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass


def test_embedding_migration_up_down():
    print("\n--- TEST: Alembic Phase 06 Migration Upgrade & Downgrade ---")
    cleanup()

    sqlite_url = f"sqlite:///{TEST_DB_PATH}"
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url)

    # 1. Upgrade to head (includes baseline + create_product_embeddings_table)
    print("Upgrading test database to head...")
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(sqlite_url)
    insp = inspect(engine)
    tables = insp.get_table_names()
    print("Tables at head:", tables)
    assert "product_embeddings" in tables
    assert "products" in tables
    assert "categories" in tables
    assert "images" in tables
    assert "ai_generations" in tables
    assert "product_metadata" in tables

    # Check columns on product_embeddings
    cols = [c["name"] for c in insp.get_columns("product_embeddings")]
    print("product_embeddings columns:", cols)
    for expected_col in [
        "id", "product_id", "vector_id", "content_hash",
        "embedding_model", "embedding_dimension", "builder_version",
        "status", "error_message", "created_at", "updated_at"
    ]:
        assert expected_col in cols, f"Missing column: {expected_col}"

    # 2. Downgrade by 1 revision (back to Phase 01-05 baseline a2c0bda2164d)
    print("Downgrading test database by -1 revision...")
    command.downgrade(alembic_cfg, "-1")

    insp = inspect(engine)
    tables_after = insp.get_table_names()
    print("Tables after downgrade -1:", tables_after)
    assert "product_embeddings" not in tables_after, "product_embeddings must be dropped"
    assert "products" in tables_after, "products table must remain"
    assert "categories" in tables_after, "categories table must remain"
    assert "images" in tables_after, "images table must remain"
    assert "ai_generations" in tables_after, "ai_generations table must remain"
    assert "product_metadata" in tables_after, "product_metadata table must remain"

    engine.dispose()
    cleanup()
    print("[PASS] Alembic upgrade to Phase 06 and clean downgrade -1 to baseline verified.")


if __name__ == "__main__":
    test_embedding_migration_up_down()
