import sys
sys.path.insert(0, ".")

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# 1. Root
res_root = client.get("/")
print("Root GET:", res_root.status_code, res_root.json())
assert res_root.status_code == 200

# 2. Categories
res_cat = client.get("/categories")
print("Categories GET:", res_cat.status_code, f"count={len(res_cat.json())}")
assert res_cat.status_code == 200

# 3. Products
res_prod = client.get("/products")
print("Products GET:", res_prod.status_code, f"count={len(res_prod.json())}")
assert res_prod.status_code == 200

print("\nALL EXISTING ENDPOINTS FUNCTIONING NORMALLY!")
