"""FastAPI Application Main Entrypoint.

Phase 10: Production Hardening
- Lifespan startup validation: critical MySQL probe + FAISS index & metadata validation (Q98)
- Safe global error handling with sanitized error schema and zero stack-trace leakage
- Request ID tracing middleware (X-Request-ID)
- Explicit configurable CORS middleware
- Health, liveness, and readiness probes (/live, /health, /ready)
"""

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.ai_generation import router as ai_generation_router
from app.api.category import router as category_router
from app.api.health import router as health_router
from app.api.image import router as image_router
from app.api.product import router as product_router
from app.api.rag import router as rag_router
from app.api.recommendation import router as recommendation_router
from app.api.search import router as search_router
from app.core.config import settings
from app.core.middleware import (
    RequestIDMiddleware,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.db.database import SessionLocal
import app.models
from app.services.faiss_lifecycle_manager import lifecycle_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for application startup and shutdown."""
    logger.info(f"Initializing {settings.app_name} v{settings.app_version}...")

    # Startup validation: validate critical MySQL and check FAISS index compatibility
    db = SessionLocal()
    try:
        lifecycle_manager.validate_on_startup(db)
    except Exception as e:
        logger.error(f"Startup validation error: {e}", exc_info=True)
    finally:
        db.close()

    yield

    logger.info(f"Shutting down {settings.app_name} gracefully.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# 1. CORS Middleware with explicit configurable origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# 2. Request ID Tracing Middleware
app.add_middleware(RequestIDMiddleware)

# 3. Safe Global Exception Handlers
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# 4. API Routers
app.include_router(health_router)
app.include_router(category_router)
app.include_router(product_router)
app.include_router(image_router)
app.include_router(ai_generation_router)
app.include_router(search_router)
app.include_router(rag_router)
app.include_router(recommendation_router)

# 5. Static Files Mounting
app.mount(
    "/uploads",
    StaticFiles(directory="uploads"),
    name="uploads"
)


@app.get("/")
def root():
    """Sanitized root endpoint with minimal diagnostic exposure."""
    return {
        "message": settings.app_name,
        "version": settings.app_version
    }