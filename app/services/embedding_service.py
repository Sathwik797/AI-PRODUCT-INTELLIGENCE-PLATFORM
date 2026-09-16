"""Product Embedding Lifecycle & Orchestration Service.

Phase 06: Implements Q41–Q44, Q49.
Orchestrates deterministic document generation, SHA-256 hash invalidation,
concurrency hash-gating, asynchronous execution, and FAISS vector store synchronization.
"""

import hashlib
import logging
import time
from typing import Any, Optional
import uuid

from sqlalchemy.orm import Session

from app.ai.embedding_provider import EmbeddingProvider, GoogleGeminiEmbeddingProvider
from app.ai.embedding_text_builder import BUILDER_VERSION, EmbeddingTextBuilder, compute_content_hash
from app.db.database import SessionLocal
from app.models.ai_generation import AIGeneration
from app.models.product import Product
from app.models.product_embedding import ProductEmbedding
from app.models.product_metadata import ProductMetadata
from app.repositories.product_embedding_repository import ProductEmbeddingRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.product_embedding import EmbeddingConfig, EmbeddingStatus
from app.vector_store.base import VectorStore
from app.vector_store.faiss_store import FAISSVectorStore

logger = logging.getLogger(__name__)


# ==============================================================================
# DOMAIN EXCEPTIONS
# ==============================================================================

class EmbeddingServiceError(Exception):
    """Base exception for all embedding service operations."""
    pass


class ProductNotFoundError(EmbeddingServiceError, ValueError):
    """Raised when the specified product does not exist."""
    pass


class ConcurrencyHashMismatchError(EmbeddingServiceError):
    """Raised when an async job detects a newer semantic representation."""
    pass


# ==============================================================================
# VECTOR ID GENERATOR (Position-Independent)
# ==============================================================================

def generate_position_independent_vector_id(product_id: int) -> int:
    """Generates a position-independent 63-bit positive integer for FAISS IndexIDMap2.

    Guarantees vector_id != product_id while ensuring deterministic bounds
    and distinct non-colliding IDs across regeneration cycles.
    """
    salt = uuid.uuid4().hex[:8]
    seed = f"{product_id}_{time.time_ns()}_{salt}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    # 63-bit positive int
    val = int(digest[:15], 16) & 0x7FFFFFFFFFFFFFFF
    # Guarantee not equal to product_id
    if val == product_id:
        val += 1
    return val


# ==============================================================================
# EMBEDDING SERVICE
# ==============================================================================

class EmbeddingService:
    """Service orchestrating product embedding generation, lifecycle, and store sync."""

    def __init__(
        self,
        product_repository: Optional[ProductRepository] = None,
        embedding_repository: Optional[ProductEmbeddingRepository] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        vector_store: Optional[VectorStore] = None,
        config: Optional[EmbeddingConfig] = None
    ):
        self.product_repository = product_repository or ProductRepository()
        self.embedding_repository = embedding_repository or ProductEmbeddingRepository()
        self.config = config or EmbeddingConfig()
        self.provider = embedding_provider or GoogleGeminiEmbeddingProvider(
            model_name=self.config.model,
            dimension=self.config.dimension
        )
        self.vector_store = vector_store or FAISSVectorStore(
            dimension=self.config.dimension
        )

    def get_accepted_ai_metadata(self, db: Session, product_id: int) -> dict[str, Any]:
        """Retrieves only accepted or modified non-canonical discovery metadata for a product.

        Strictly excludes rejected, pending, or unaccepted historical generations.
        """
        meta = (
            db.query(ProductMetadata)
            .filter(ProductMetadata.product_id == product_id)
            .first()
        )
        if not meta or not meta.current_generation_id:
            return {}

        generation = (
            db.query(AIGeneration)
            .filter(AIGeneration.id == meta.current_generation_id)
            .first()
        )
        if not generation or not generation.output or not generation.acceptance_state:
            return {}

        acc_state = generation.acceptance_state
        output = generation.output
        accepted_dict: dict[str, Any] = {}

        # Tags
        if acc_state.get("tags") in ("accepted", "modified"):
            accepted_dict["tags"] = output.get("tags", [])

        # Keywords
        if acc_state.get("keywords") in ("accepted", "modified"):
            accepted_dict["keywords"] = output.get("keywords", [])

        # Attributes
        if acc_state.get("attributes") in ("accepted", "modified"):
            accepted_dict["attributes"] = output.get("attributes", {})

        return accepted_dict

    def build_embedding_document(self, db: Session, product: Product) -> tuple[str, str]:
        """Compiles deterministic embedding text and its SHA-256 content hash."""
        accepted_meta = self.get_accepted_ai_metadata(db, product.id)
        cat_name = product.category.name if product.category else None
        text = EmbeddingTextBuilder.build(
            product=product,
            accepted_metadata=accepted_meta,
            category_name=cat_name
        )
        content_hash = compute_content_hash(text)
        return text, content_hash

    def invalidate_embedding(
        self,
        db: Session,
        product_id: int,
        commit: bool = True
    ) -> Optional[ProductEmbedding]:
        """Transitions an existing READY embedding to STALE upon semantic change."""
        emb = self.embedding_repository.get_by_product_id(db, product_id)
        if emb and emb.status == EmbeddingStatus.READY.value:
            emb.status = EmbeddingStatus.STALE.value
            self.embedding_repository.update(db, emb, commit=commit)
            logger.info(f"Invalidated embedding for product {product_id} -> STALE")
        return emb

    def generate_product_embedding(
        self,
        db: Session,
        product_id: int,
        expected_hash: Optional[str] = None
    ) -> ProductEmbedding:
        """Generates or updates a product embedding with content-hash concurrency gating.

        Implements Q38, Q40, Q41, Q44.
        """
        product = self.product_repository.get_by_id(db, product_id)
        if not product:
            raise ProductNotFoundError(f"Product with ID {product_id} not found.")

        # 1. Re-read authoritative state & re-compute SHA-256 hash
        text, current_hash = self.build_embedding_document(db, product)

        # 2. Concurrency hash-gate (Q44)
        if expected_hash is not None and current_hash != expected_hash:
            logger.warning(
                f"Concurrency hash mismatch for product {product_id}: "
                f"job expected {expected_hash}, current is {current_hash}."
            )
            # Mark STALE to allow newer job to run, and do NOT commit old vector
            emb = self.embedding_repository.get_by_product_id(db, product_id)
            if emb:
                emb.status = EmbeddingStatus.STALE.value
                self.embedding_repository.update(db, emb, commit=True)
            raise ConcurrencyHashMismatchError(
                f"Product {product_id} state changed since async job was queued."
            )

        # 3. Check existing embedding record
        emb = self.embedding_repository.get_by_product_id(db, product_id)

        # 4. Hash unchanged & already READY => Skip (Q38)
        if (
            emb is not None
            and emb.status == EmbeddingStatus.READY.value
            and emb.content_hash == current_hash
            and emb.embedding_model == self.provider.get_model_name()
            and emb.builder_version == BUILDER_VERSION
        ):
            # Verify vector store integrity (self-healing)
            if not self.vector_store.contains(emb.vector_id):
                logger.info(f"Restoring missing vector {emb.vector_id} to vector store for product {product_id}")
                vector = self.provider.embed_text(text)
                self.vector_store.add_vector(emb.vector_id, vector)
            logger.info(f"Embedding for product {product_id} is already up-to-date (hash={current_hash}). Skipping.")
            return emb

        # 5. Prepare record in GENERATING status
        # Remember previous valid vector_id (if any) to guarantee it is NOT destroyed on failure
        old_vector_id = emb.vector_id if emb else None
        # Allocate a new position-independent vector_id for this generation attempt
        new_vector_id = generate_position_independent_vector_id(product_id)

        if not emb:
            emb = ProductEmbedding(
                product_id=product_id,
                vector_id=new_vector_id,
                content_hash=current_hash,
                embedding_model=self.provider.get_model_name(),
                embedding_dimension=self.provider.get_dimension(),
                builder_version=BUILDER_VERSION,
                status=EmbeddingStatus.GENERATING.value,
                error_message=None
            )
            emb = self.embedding_repository.create(db, emb, commit=True)
        else:
            emb.status = EmbeddingStatus.GENERATING.value
            # Do NOT update emb.content_hash or emb.vector_id yet!
            # Keep previous hash and vector_id intact until generation succeeds
            emb.error_message = None
            emb = self.embedding_repository.update(db, emb, commit=True)

        # 6. Call Provider & VectorStore with Failure Protection
        try:
            vector = self.provider.embed_text(text)
            self.vector_store.add_vector(new_vector_id, vector)

            # Pre-commit Concurrency Gate (Q44):
            # Reset transaction snapshot so MySQL InnoDB reads the latest committed state,
            # guaranteeing no newer semantic edit occurred while the provider network call was in flight.
            db.commit()
            fresh_product = self.product_repository.get_by_id(db, product_id)
            _, latest_hash = self.build_embedding_document(db, fresh_product)
            if latest_hash != current_hash:
                logger.warning(
                    f"Concurrent modification detected before commit for product {product_id}: "
                    f"generated hash {current_hash}, latest is {latest_hash}."
                )
                # Clean up new vector from FAISS since it is already superseded
                if self.vector_store.contains(new_vector_id):
                    self.vector_store.remove_vector(new_vector_id)
                emb.status = EmbeddingStatus.STALE.value
                self.embedding_repository.update(db, emb, commit=True)
                raise ConcurrencyHashMismatchError(
                    f"Product {product_id} was modified concurrently during embedding generation."
                )

            # Commit authoritative READY state in MySQL
            emb.vector_id = new_vector_id
            emb.content_hash = current_hash
            emb.status = EmbeddingStatus.READY.value
            emb.error_message = None
            emb.builder_version = BUILDER_VERSION
            emb.embedding_model = self.provider.get_model_name()
            emb.embedding_dimension = self.provider.get_dimension()
            self.embedding_repository.update(db, emb, commit=True)
            logger.info(f"Successfully generated READY embedding for product {product_id} (vector_id={new_vector_id})")

            # Post-commit: Clean up old vector from vector store now that new vector is authoritative
            if old_vector_id is not None and old_vector_id != new_vector_id:
                try:
                    self.vector_store.remove_vector(old_vector_id)
                except Exception as cleanup_err:
                    logger.warning(f"Failed to remove superseded vector {old_vector_id} from vector store: {cleanup_err}")

            return emb

        except ConcurrencyHashMismatchError:
            # Status was already marked STALE and temporary vector removed; propagate directly
            raise
        except Exception as e:
            logger.error(f"Failed to generate embedding for product {product_id}: {e}")
            # If new_vector_id was written to FAISS before failure, clean it up
            if self.vector_store.contains(new_vector_id):
                try:
                    self.vector_store.remove_vector(new_vector_id)
                except Exception:
                    pass
            # Rollback any aborted transaction and mark record as FAILED
            try:
                db.rollback()
                emb = self.embedding_repository.get_by_product_id(db, product_id)
                if emb:
                    emb.status = EmbeddingStatus.FAILED.value
                    emb.error_message = str(e)[:1000]
                    self.embedding_repository.update(db, emb, commit=True)
            except Exception as db_err:
                logger.error(f"Failed to record FAILED status for product {product_id}: {db_err}")
            raise

    def reconcile_with_vector_store(self, db: Session) -> dict[str, int]:
        """Audits and heals discrepancy between authoritative MySQL records and FAISS.

        Implements Q48 & consistency audit requirements:
        1. MySQL READY + FAISS missing -> repaired (re-embed & restore to FAISS)
        2. FAISS orphan vector -> detected and purged from FAISS
        3. Stale/failed records in MySQL are never treated as authoritative vectors.
        """
        ready_embeddings = self.embedding_repository.list_all_ready(db)
        total_ready = len(ready_embeddings)
        ready_vector_ids = {emb.vector_id for emb in ready_embeddings}

        store_vector_ids = set(self.vector_store.list_vector_ids())

        missing_in_store = 0
        restored = 0
        orphans_removed = 0

        # Case 1: MySQL READY + FAISS missing -> restore
        for emb in ready_embeddings:
            if emb.vector_id not in store_vector_ids:
                missing_in_store += 1
                product = self.product_repository.get_by_id(db, emb.product_id)
                if product:
                    try:
                        text, _ = self.build_embedding_document(db, product)
                        vector = self.provider.embed_text(text)
                        self.vector_store.add_vector(emb.vector_id, vector)
                        restored += 1
                    except Exception as e:
                        logger.error(f"Reconciliation restore failed for product {emb.product_id}: {e}")

        # Case 2: FAISS orphan vectors (present in FAISS but not READY in MySQL) -> prune
        orphan_ids = store_vector_ids - ready_vector_ids
        for orphan_id in orphan_ids:
            try:
                self.vector_store.remove_vector(orphan_id)
                orphans_removed += 1
                logger.info(f"Pruned orphan vector {orphan_id} from vector store.")
            except Exception as e:
                logger.error(f"Failed to remove orphan vector {orphan_id} from store: {e}")

        return {
            "ready_in_db": total_ready,
            "vector_store_count": self.vector_store.count(),
            "missing_in_vector_store": missing_in_store,
            "restored_in_vector_store": restored,
            "orphans_removed": orphans_removed,
        }

    def rebuild_all_embeddings(self, db: Session) -> dict[str, int]:
        """Atomically rebuilds the FAISS vector index from all eligible products."""
        products = self.product_repository.get_all(db)
        rebuilt_vectors: list[tuple[int, list[float]]] = []
        success_count = 0
        failed_count = 0

        for product in products:
            try:
                emb = self.generate_product_embedding(db, product.id)
                vec = self.vector_store.get_vector(emb.vector_id)
                if vec is not None:
                    rebuilt_vectors.append((emb.vector_id, vec))
                success_count += 1
            except Exception as e:
                logger.error(f"Rebuild failed for product {product.id}: {e}")
                failed_count += 1

        # Atomically rebuild index
        self.vector_store.rebuild(rebuilt_vectors)

        return {
            "total_products": len(products),
            "rebuilt_successful": success_count,
            "rebuilt_failed": failed_count,
            "index_total": self.vector_store.count()
        }


# ==============================================================================
# ASYNC BACKGROUND TASK ADAPTER (FastAPI BackgroundTasks)
# ==============================================================================

def run_async_product_embedding(
    product_id: int,
    expected_hash: str,
    provider: Optional[EmbeddingProvider] = None,
    store: Optional[VectorStore] = None
) -> None:
    """Entry point for FastAPI BackgroundTasks executing in an isolated database session."""
    db: Session = SessionLocal()
    try:
        service = EmbeddingService(
            embedding_provider=provider,
            vector_store=store
        )
        service.generate_product_embedding(db, product_id, expected_hash=expected_hash)
    except ConcurrencyHashMismatchError:
        logger.info(f"Background embedding skipped due to hash mismatch for product {product_id}")
    except Exception as e:
        logger.error(f"Background embedding task failed for product {product_id}: {e}")
    finally:
        db.close()
