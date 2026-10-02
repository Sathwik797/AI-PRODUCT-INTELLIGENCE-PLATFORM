"""Production entrypoint for Render and cloud container deployments."""
import os
import subprocess
import sys


# Ensure project root is in sys.path and PYTHONPATH
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
os.environ["PYTHONPATH"] = f"{ROOT_DIR}:{os.environ.get('PYTHONPATH', '')}"


def main():
    port = int(os.environ.get("PORT", "8000"))
    print(f"[STARTUP] Initializing application on port {port}...")

    # Ensure required runtime directories exist
    os.makedirs("data/faiss", exist_ok=True)
    os.makedirs("uploads/products", exist_ok=True)

    # 1. Initialize database tables automatically (works for SQLite, MySQL, Postgres)
    print("[STARTUP] Initializing database tables...")
    try:
        from app.db.base import Base
        from app.db.database import engine, DATABASE_URL
        import app.models
        print(f"[STARTUP] Connected to database: {DATABASE_URL}")
        Base.metadata.create_all(bind=engine)
        print("[STARTUP] Database tables verified/created successfully.")
    except Exception as e:
        print(f"[STARTUP] Table creation note: {e}")

    # 2. Run Alembic migrations if using a remote MySQL/Postgres database
    try:
        from app.db.database import DATABASE_URL
        if not str(DATABASE_URL).startswith("sqlite"):
            print("[STARTUP] Running Alembic migrations for remote database...")
            subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=False)
    except Exception as e:
        print(f"[STARTUP] Alembic notice: {e}")

    # 3. Auto-seed demo products if database is newly initialized and empty
    try:
        from app.db.database import SessionLocal
        from app.models.product import Product
        db = SessionLocal()
        product_count = db.query(Product).count()
        db.close()
        if product_count == 0:
            print("[STARTUP] Database has 0 products. Auto-seeding initial demo catalog...")
            from scripts.seed_demo_storefront import seed_demo_storefront
            seed_demo_storefront()
            print("[STARTUP] Demo products seeded successfully!")
    except Exception as e:
        print(f"[STARTUP] Demo seed note (non-fatal): {e}")

    # 4. Launch Uvicorn ASGI Server
    print(f"[STARTUP] Launching Uvicorn server on 0.0.0.0:{port}...")
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
