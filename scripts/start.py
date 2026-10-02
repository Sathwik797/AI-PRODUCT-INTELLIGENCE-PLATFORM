"""Production entrypoint for Render and cloud container deployments."""
import os
import subprocess
import sys


def main():
    port = int(os.environ.get("PORT", "8000"))
    print(f"[STARTUP] Initializing application on port {port}...")

    # Run database migrations if DB is configured
    print("[STARTUP] Checking and applying database migrations (alembic upgrade head)...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            check=False,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("[STARTUP] Database migrations applied successfully.")
            if result.stdout.strip():
                print(result.stdout)
        else:
            print(f"[STARTUP] Alembic migration notice (non-fatal): {result.stderr or result.stdout}")
    except Exception as e:
        print(f"[STARTUP] Warning during migrations: {e}")

    # Launch Uvicorn
    print(f"[STARTUP] Launching Uvicorn ASGI server on 0.0.0.0:{port}...")
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
