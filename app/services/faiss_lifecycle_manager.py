"""FAISS Startup Validation & Recovery Lifecycle Manager.

Phase 10: Implements Q98 (Option C):
- Validates critical MySQL dependency on startup.
- Validates FAISS vector store dimension, metadata configuration, and EXACT vector ID set against MySQL READY embeddings.
- If healthy: serves semantic capability immediately.
- If missing, stale, or corrupt: marks semantic capability unavailable without blocking API startup,
  and triggers background reconciliation with atomic index reload and single-execution concurrency lock.
"""

import json
import logging
from pathlib import Path
import threading
import time
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.product_embedding import ProductEmbedding
from app.services.embedding_service import EmbeddingService
from app.vector_store.base import VectorStore
from app.vector_store.faiss_store import FAISSVectorStore

logger = logging.getLogger(__name__)


class FAISSLifecycleManager:
    """Manages the boot-time validation, health state, and asynchronous reconciliation of FAISS."""

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        embedding_service: Optional[EmbeddingService] = None,
        dimension: int = 768
    ):
        self.vector_store = vector_store or FAISSVectorStore(dimension=dimension)
        self.embedding_service = embedding_service or EmbeddingService(vector_store=self.vector_store)
        self.dimension = dimension

        self._semantic_available = False
        self._state = "uninitialized"  # "healthy", "reconciling", "degraded", "critical"
        self._rebuild_lock = threading.Lock()
        self._last_validation: dict[str, Any] = {}

    @property
    def is_semantic_available(self) -> bool:
        """Returns whether the semantic vector store is currently healthy and authoritative."""
        return self._semantic_available

    @property
    def state(self) -> str:
        """Returns the current vector store health lifecycle state."""
        return self._state

    @property
    def last_validation(self) -> dict[str, Any]:
        """Returns diagnostic details from the most recent validation check."""
        return self._last_validation

    def validate_mysql(self, db: Session) -> bool:
        """Probes the critical MySQL database dependency."""
        try:
            db.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Critical database probe failed: {e}")
            return False

    def validate_faiss(self, db: Session) -> tuple[bool, dict[str, Any]]:
        """Strictly validates FAISS against expected MySQL READY vector IDs, dimension, and metadata."""
        diagnostics: dict[str, Any] = {
            "metadata_valid": False,
            "dimension_match": False,
            "mysql_ready_count": 0,
            "faiss_count": 0,
            "id_set_match": False,
            "missing_in_faiss_count": 0,
            "orphan_in_faiss_count": 0,
            "errors": []
        }

        # 1. Metadata and File Existence Check
        meta_path = getattr(self.vector_store, "metadata_path", None)
        index_path = getattr(self.vector_store, "index_path", None)

        if not index_path or not Path(index_path).exists():
            diagnostics["errors"].append("FAISS index file does not exist on disk.")
            return False, diagnostics

        if meta_path and Path(meta_path).exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta_dim = meta.get("dimension")
                if meta_dim == self.dimension:
                    diagnostics["metadata_valid"] = True
                    diagnostics["dimension_match"] = True
                else:
                    diagnostics["errors"].append(
                        f"Persisted dimension mismatch: expected {self.dimension}, got {meta_dim}."
                    )
                    return False, diagnostics
            except Exception as e:
                diagnostics["errors"].append(f"Failed to read FAISS metadata: {e}")
                return False, diagnostics
        else:
            diagnostics["errors"].append("FAISS metadata.json does not exist on disk.")
            return False, diagnostics

        # 2. Extract expected READY vector IDs from MySQL
        try:
            ready_rows = (
                db.query(ProductEmbedding.vector_id)
                .filter(ProductEmbedding.status == "READY")
                .all()
            )
            expected_ids = {r[0] for r in ready_rows}
            diagnostics["mysql_ready_count"] = len(expected_ids)
        except Exception as e:
            diagnostics["errors"].append(f"Failed to query MySQL READY vector IDs: {e}")
            return False, diagnostics

        # 3. Extract actual vector IDs from FAISS index
        try:
            store_ids = set(self.vector_store.list_vector_ids())
            diagnostics["faiss_count"] = len(store_ids)
        except Exception as e:
            diagnostics["errors"].append(f"Failed to list vector IDs from FAISS index: {e}")
            return False, diagnostics

        # 4. Exact ID-set comparison
        missing = expected_ids - store_ids
        orphans = store_ids - expected_ids
        diagnostics["missing_in_faiss_count"] = len(missing)
        diagnostics["orphan_in_faiss_count"] = len(orphans)

        if missing or orphans:
            diagnostics["id_set_match"] = False
            diagnostics["errors"].append(
                f"FAISS ID-set discrepancy: {len(missing)} missing, {len(orphans)} orphan vectors."
            )
            return False, diagnostics

        diagnostics["id_set_match"] = True
        return True, diagnostics

    def validate_on_startup(self, db: Session) -> dict[str, Any]:
        """Executes Q98 startup validation.
        
        If FAISS is missing or out-of-sync, marks semantic capability unavailable
        and triggers non-blocking asynchronous reconciliation.
        """
        mysql_healthy = self.validate_mysql(db)
        if not mysql_healthy:
            self._state = "critical"
            self._semantic_available = False
            self._last_validation = {"mysql_healthy": False, "faiss_healthy": False, "status": "critical"}
            return self._last_validation

        faiss_healthy, faiss_diag = self.validate_faiss(db)
        self._last_validation = {
            "mysql_healthy": True,
            "faiss_healthy": faiss_healthy,
            "faiss_diagnostics": faiss_diag
        }

        if faiss_healthy:
            self._semantic_available = True
            self._state = "healthy"
            logger.info("FAISS index startup validation PASSED: semantic search is fully available.")
        else:
            self._semantic_available = False
            self._state = "reconciling"
            logger.warning(
                f"FAISS startup validation detected discrepancy ({faiss_diag['errors']}). "
                "Semantic search temporarily disabled; triggering asynchronous reconciliation."
            )
            self.trigger_async_reconciliation(SessionLocal)

        return self._last_validation

    def trigger_async_reconciliation(
        self,
        session_factory: Callable[[], Session]
    ) -> bool:
        """Spawns an asynchronous background worker to reconcile and atomically reload FAISS.
        
        Guarantees a single concurrency lock to prevent duplicate simultaneous rebuild jobs.
        """
        if self._rebuild_lock.locked():
            logger.info("FAISS reconciliation is already running. Skipping duplicate trigger.")
            return False

        def _worker():
            with self._rebuild_lock:
                self._state = "reconciling"
                db = session_factory()
                try:
                    logger.info("Beginning asynchronous FAISS reconciliation against MySQL...")
                    res = self.embedding_service.reconcile_with_vector_store(db)
                    logger.info(f"Reconciliation completed: {res}")

                    # Re-validate
                    is_now_healthy, _ = self.validate_faiss(db)
                    if is_now_healthy:
                        self._semantic_available = True
                        self._state = "healthy"
                        logger.info("FAISS capability restored successfully; semantic search enabled.")
                    else:
                        self._semantic_available = False
                        self._state = "degraded"
                        logger.error("FAISS reconciliation finished but index remains out-of-sync.")
                except Exception as e:
                    self._semantic_available = False
                    self._state = "degraded"
                    logger.error(f"Asynchronous FAISS reconciliation encountered an error: {e}", exc_info=True)
                finally:
                    db.close()

        thread = threading.Thread(target=_worker, daemon=True, name="FAISSReconciler")
        thread.start()
        return True


# Global shared lifecycle manager instance
lifecycle_manager = FAISSLifecycleManager()
