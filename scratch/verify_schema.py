import sys
sys.path.insert(0, ".")

from app.db.database import engine
from sqlalchemy import inspect

inspector = inspect(engine)

print("=== AI_GENERATIONS COLUMNS ===")
for col in inspector.get_columns("ai_generations"):
    print(f"{col['name']}: {col['type']} (nullable={col['nullable']})")

print("\n=== AI_GENERATIONS FOREIGN KEYS ===")
for fk in inspector.get_foreign_keys("ai_generations"):
    print(fk)

print("\n=== PRODUCT_METADATA COLUMNS ===")
for col in inspector.get_columns("product_metadata"):
    print(f"{col['name']}: {col['type']} (nullable={col['nullable']})")

print("\n=== PRODUCT_METADATA FOREIGN KEYS ===")
for fk in inspector.get_foreign_keys("product_metadata"):
    print(fk)

print("\n=== PRODUCT_METADATA UNIQUE CONSTRAINTS / INDEXES ===")
for uc in inspector.get_unique_constraints("product_metadata"):
    print("Unique constraint:", uc)
for idx in inspector.get_indexes("product_metadata"):
    print("Index:", idx)
