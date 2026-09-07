"""AI Generation Service for AI Product Intelligence Platform.

Phase 05 – Step 5: AI Generation Business & Orchestration Layer.

Orchestrates the end-to-end lifecycle of an AI product metadata generation run:
- Validates product existence in transactional domain.
- Assembles domain context (Product, Images, Categories) via AIProductContextBuilder.
- Maintains strict generation lifecycle state machine: pending -> processing -> completed / failed.
- Enforces monotonically increasing generation numbering across attempts.
- Coordinates successful generation completion and ProductMetadata current pointer
  atomically within the same database transaction.
- Prevents failed generations from updating the active draft pointer.
- Measures elapsed processing duration using a monotonic clock.
- Initializes field-level seller acceptance state.
"""

from datetime import datetime, timezone
import time
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.ai.context_builder import AIProductContextBuilder
from app.ai.gemini_provider import GeminiProvider
from app.models.ai_generation import AIGeneration
from app.repositories.ai_generation_repository import AIGenerationRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.image_repository import ImageRepository
from app.repositories.product_metadata_repository import ProductMetadataRepository
from app.repositories.product_repository import ProductRepository

# Explicit metadata version constants
PROMPT_VERSION = "v1"
SCHEMA_VERSION = "v1"


# ==============================================================================
# SERVICE EXCEPTIONS (Domain-level, zero FastAPI HTTPException dependency)
# ==============================================================================

class AIGenerationServiceError(Exception):
    """Base exception for all AI generation service errors."""
    pass


class ProductNotFoundError(AIGenerationServiceError, ValueError):
    """Raised when the specified product does not exist in the database."""
    pass


class AIGenerationExecutionError(AIGenerationServiceError):
    """Raised when AI generation execution fails (Gemini API, validation, etc.)."""
    pass


# ==============================================================================
# AI GENERATION SERVICE
# ==============================================================================

class AIGenerationService:
    """Service orchestrating AI product metadata generation lifecycle."""

    def __init__(
        self,
        product_repository: ProductRepository,
        image_repository: ImageRepository,
        category_repository: CategoryRepository,
        ai_generation_repository: AIGenerationRepository,
        product_metadata_repository: ProductMetadataRepository,
        provider: Optional[GeminiProvider] = None,
        context_builder: Optional[AIProductContextBuilder] = None,
    ):
        self.product_repository = product_repository
        self.image_repository = image_repository
        self.category_repository = category_repository
        self.ai_generation_repository = ai_generation_repository
        self.product_metadata_repository = product_metadata_repository
        self.provider = provider or GeminiProvider()
        self.context_builder = context_builder or AIProductContextBuilder()

    def generate(
        self,
        db: Session,
        product_id: int,
        image_role_overrides: Optional[dict[int, str]] = None,
        preloaded_image_bytes: Optional[dict[int, bytes]] = None,
    ) -> AIGeneration:
        """Executes a complete AI product metadata generation run for a product.

        Args:
            db: Active SQLAlchemy database session.
            product_id: Primary key of the product.
            image_role_overrides: Optional mapping of image_id -> seller role.
            preloaded_image_bytes: Optional mapping of image_id -> raw bytes.

        Returns:
            Completed AIGeneration record with persisted structured output and acceptance state.

        Raises:
            ProductNotFoundError: If the product does not exist.
            AIGenerationExecutionError: If AI generation fails (record is marked 'failed').
        """
        # 1. Validate product exists
        product = self.product_repository.get_by_id(db, product_id)
        if not product:
            raise ProductNotFoundError(f"Product with id {product_id} not found.")

        # 2. Gather domain data for AI context
        images = self.image_repository.get_by_product(db, product_id)
        categories = self.category_repository.get_all(db)

        # 3. Determine monotonically increasing generation number
        generation_number = self.ai_generation_repository.get_next_generation_number(
            db=db,
            product_id=product_id
        )

        # 4. Create initial generation record with status='pending'
        model_name = getattr(self.provider.config, "model_name", "gemini-2.5-flash")
        generation = AIGeneration(
            product_id=product_id,
            generation_number=generation_number,
            status="pending",
            model_name=model_name,
            model_version=None,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
        )
        generation = self.ai_generation_repository.create(db, generation, commit=True)

        # 5. Transition state to 'processing' when execution starts
        generation.status = "processing"
        generation.started_at = datetime.now(timezone.utc)
        self.ai_generation_repository.update(db, generation, commit=True)

        # 6. Execute AI generation with monotonic timer
        start_time = time.monotonic()
        try:
            # Assemble decoupled DTO context
            ai_context = self.context_builder.build_context(
                product=product,
                images=images,
                available_categories=categories,
                image_role_overrides=image_role_overrides,
                preloaded_image_bytes=preloaded_image_bytes,
            )

            # Invoke provider boundary
            ai_metadata = self.provider.generate_product_metadata(ai_context)

            # Serialize output to pure JSON dictionary
            output_dict = ai_metadata.model_dump(mode="json")

            # Initialize field-level seller acceptance state for all top-level fields
            acceptance_state = {key: "pending" for key in output_dict.keys()}

            # Record elapsed execution duration
            processing_time = round(time.monotonic() - start_time, 3)

            # Update generation entity attributes
            generation.status = "completed"
            generation.completed_at = datetime.now(timezone.utc)
            generation.processing_time = processing_time
            generation.output = output_dict
            generation.acceptance_state = acceptance_state
            generation.error_message = None

            # 7. Final Success Transaction Coordination:
            # Atomically commit the completed generation and the current_generation_id pointer
            # in the same database transaction so states never diverge.
            self.ai_generation_repository.update(db, generation, commit=False)
            self.product_metadata_repository.set_current_generation(
                db=db,
                product_id=product_id,
                generation_id=generation.id,
                commit=False
            )
            db.commit()
            db.refresh(generation)

            return generation

        except Exception as exc:
            # Failure Path: Record failure state, elapsed time, and error message.
            processing_time = round(time.monotonic() - start_time, 3)
            generation.status = "failed"
            generation.completed_at = datetime.now(timezone.utc)
            generation.processing_time = processing_time
            generation.error_message = str(exc)

            # Persist failure status; DO NOT update ProductMetadata.current_generation_id
            self.ai_generation_repository.update(db, generation, commit=True)

            raise AIGenerationExecutionError(
                f"AI product metadata generation failed for product {product_id}: {exc}"
            ) from exc
