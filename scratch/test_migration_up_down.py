import os
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect

def test_upgrade_downgrade():
    test_db_path = "scratch/test_migration.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    sqlite_url = f"sqlite:///{test_db_path}"
    
    # Configure alembic to use test sqlite DB
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url)
    
    # 1. Upgrade to head
    print("Testing alembic upgrade head on test database...")
    command.upgrade(alembic_cfg, "head")
    
    test_engine = create_engine(sqlite_url)
    insp = inspect(test_engine)
    tables = insp.get_table_names()
    print("Tables created after upgrade head:", tables)
    assert "categories" in tables
    assert "products" in tables
    assert "images" in tables
    assert "ai_generations" in tables
    assert "product_metadata" in tables
    assert "alembic_version" in tables
    print("PASS: upgrade head successfully created all expected Phase 01-05 tables.")
    
    # 2. Downgrade to base (-1)
    print("Testing alembic downgrade -1 on test database...")
    command.downgrade(alembic_cfg, "-1")
    
    insp = inspect(test_engine)
    tables_after = insp.get_table_names()
    print("Tables remaining after downgrade -1:", tables_after)
    assert "categories" not in tables_after
    assert "products" not in tables_after
    assert "images" not in tables_after
    assert "ai_generations" not in tables_after
    assert "product_metadata" not in tables_after
    print("PASS: downgrade -1 successfully removed all baseline tables.")
    
    # Clean up test db
    test_engine.dispose()
    try:
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
    except Exception:
        pass
    print("All migration up/down verifications passed!")

if __name__ == "__main__":
    test_upgrade_downgrade()
