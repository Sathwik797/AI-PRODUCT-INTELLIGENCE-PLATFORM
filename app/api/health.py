"""Health, Liveness, and Readiness Endpoints for Phase 10 Production Hardening.

Semantics:
- GET /live: Returns process liveness.
- GET /health: Returns basic application status and version.
- GET /ready: Probes critical dependencies (MySQL) and capability dependencies (FAISS).
  MySQL is mandatory for readiness (returns 503 if down).
  FAISS is a capability dependency (returns 200 with degraded semantic_search if reconciling/unavailable).
"""

import logging
from typing import Any
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.dependencies import get_db
from app.services.faiss_lifecycle_manager import lifecycle_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/live")
def liveness_probe() -> dict[str, str]:
    """Liveness probe: verifies that the FastAPI process is running."""
    return {"status": "alive"}


@router.get("/health")
def health_probe() -> dict[str, Any]:
    """Health probe: returns basic application service health."""
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "app_version": settings.app_version
    }


@router.get("/ready")
def readiness_probe(
    response: Response,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Readiness probe: determines if the instance can safely serve traffic.
    
    - MySQL is critical: if down, returns HTTP 503.
    - FAISS is a capability dependency: if reconciling/degraded, returns HTTP 200 with semantic_search: false.
    """
    mysql_ok = lifecycle_manager.validate_mysql(db)
    faiss_state = lifecycle_manager.state
    semantic_available = lifecycle_manager.is_semantic_available

    if not mysql_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "dependencies": {
                "mysql": "unhealthy",
                "faiss": faiss_state
            },
            "capabilities": {
                "structured_search": False,
                "semantic_search": False
            }
        }

    return {
        "status": "ready",
        "dependencies": {
            "mysql": "healthy",
            "faiss": faiss_state
        },
        "capabilities": {
            "structured_search": True,
            "semantic_search": semantic_available
        }
    }
