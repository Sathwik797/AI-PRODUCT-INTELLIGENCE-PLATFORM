"""AI Metadata Acceptance & Seller Review Service.

Phase 05 – Step 7: Human-in-the-Loop Review Boundary.

Orchestrates seller acceptance, granular modification, and rejection of AI-generated
product metadata while preserving:
- Zero direct AI overwrite of canonical Product data without seller approval.
- Immutability of historical AIGeneration.output records.
- Atomic database transaction coordination across Product and AIGeneration tables.
- Accurate distinction between canonical columns (title, description, brand, category_id)
  and non-canonical discovery metadata (tags, keywords, attributes).
- Automatic synchronization: when a seller manually edits a canonical product field
  that was previously accepted from the active AI generation, that field's state
  transitions to 'modified'.
"""

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.ai_generation import AIGeneration
from app.models.product import Product
from app.repositories.ai_generation_repository import AIGenerationRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.product_metadata_repository import ProductMetadataRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.ai_generation import (
    AIAcceptanceResponse,
    FieldReviewAction,
    FieldReviewDecision,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# DOMAIN EXCEPTIONS (Zero FastAPI HTTPException coupling)
# ==============================================================================

class AIAcceptanceServiceError(Exception):
    """Base domain exception for AI acceptance and review operations."""
    pass


class ProductNotFoundError(AIAcceptanceServiceError, ValueError):
    """Raised when the specified product does not exist."""
    pass


class NoActiveGenerationError(AIAcceptanceServiceError, ValueError):
    """Raised when a product has no active AI generation record."""
    pass


class InvalidGenerationStateError(AIAcceptanceServiceError, ValueError):
    """Raised when attempting to review a generation that is not in completed status."""
    pass


class AcceptanceValidationError(AIAcceptanceServiceError, ValueError):
    """Raised when review input data fails field-specific business validation."""
    pass


# ==============================================================================
# AI ACCEPTANCE SERVICE
# ==============================================================================

class AIAcceptanceService:
    """Service orchestrating seller review and acceptance of AI product metadata."""

    def __init__(
        self,
        product_repository: ProductRepository,
        ai_generation_repository: AIGenerationRepository,
        product_metadata_repository: ProductMetadataRepository,
        category_repository: CategoryRepository,
        embedding_service: Optional[Any] = None,
    ):
        self.product_repository = product_repository
        self.ai_generation_repository = ai_generation_repository
        self.product_metadata_repository = product_metadata_repository
        self.category_repository = category_repository
        self.embedding_service = embedding_service

    def get_active_generation(
        self,
        db: Session,
        product_id: int
    ) -> AIGeneration:
        """Retrieves and validates the active completed AI generation for a product.

        Args:
            db: Active SQLAlchemy database session.
            product_id: Primary key of the product.

        Returns:
            The active AIGeneration entity.

        Raises:
            ProductNotFoundError: If the product does not exist.
            NoActiveGenerationError: If no active generation pointer exists.
            InvalidGenerationStateError: If the active generation is not 'completed'.
        """
        product = self.product_repository.get_by_id(db, product_id)
        if not product:
            raise ProductNotFoundError(f"Product with id {product_id} not found.")

        meta = self.product_metadata_repository.get_by_product_id(db, product_id)
        if not meta or not meta.current_generation_id:
            raise NoActiveGenerationError(f"No active AI generation found for product {product_id}.")

        generation = self.ai_generation_repository.get_by_id(db, meta.current_generation_id)
        if not generation or generation.product_id != product_id:
            raise NoActiveGenerationError(
                f"Active generation {meta.current_generation_id} not found for product {product_id}."
            )

        if generation.status != "completed" or not generation.output:
            raise InvalidGenerationStateError(
                f"Cannot accept or review generation {generation.id} in '{generation.status}' state."
            )

        return generation

    def accept_all(
        self,
        db: Session,
        product_id: int,
        background_tasks: Optional[Any] = None
    ) -> AIAcceptanceResponse:
        """Accepts all valid AI-generated metadata for the active generation in one click.

        Copies valid canonical fields (title, description, brand, category) into the
        Product record. Non-canonical fields (tags, keywords, attributes) are marked
        'accepted' in acceptance_state for future discovery/indexing, but are NOT added
        to applied_fields.

        Args:
            db: Active SQLAlchemy database session.
            product_id: Primary key of the product.
            background_tasks: Optional FastAPI BackgroundTasks instance to schedule async embeddings.

        Returns:
            AIAcceptanceResponse with applied fields and full updated review status.
        """
        product = self.product_repository.get_by_id(db, product_id)
        if not product:
            raise ProductNotFoundError(f"Product with id {product_id} not found.")

        generation = self.get_active_generation(db, product_id)
        output = generation.output or {}
        acc_state = dict(generation.acceptance_state or {})
        applied_fields: list[str] = []

        # 1. Canonical: Title
        if output.get("title") and output["title"].get("value"):
            product.title = str(output["title"]["value"]).strip()
            acc_state["title"] = "accepted"
            applied_fields.append("title")
        else:
            acc_state["title"] = "rejected"

        # 2. Canonical: Description
        if output.get("description") and output["description"].get("value"):
            product.description = str(output["description"]["value"]).strip()
            acc_state["description"] = "accepted"
            applied_fields.append("description")
        else:
            acc_state["description"] = "rejected"

        # 3. Canonical: Brand
        if output.get("brand") and output["brand"].get("value"):
            product.brand = str(output["brand"]["value"]).strip()
            acc_state["brand"] = "accepted"
            applied_fields.append("brand")
        else:
            acc_state["brand"] = "rejected"

        # 4. Canonical: Category
        # Category resolution rule:
        # If recommended_category_id is provided and valid, use it.
        # Fallback: if only recommended_category_name is provided, match by name.
        cat_field = output.get("category")
        matched_cat_id: Optional[int] = None

        if cat_field and cat_field.get("value"):
            cat_val = cat_field["value"]
            rec_id = cat_val.get("recommended_category_id")
            rec_name = cat_val.get("recommended_category_name")

            if rec_id:
                existing_cat = self.category_repository.get_by_id(db, rec_id)
                if existing_cat:
                    matched_cat_id = existing_cat.id

            if not matched_cat_id and rec_name:
                matched_by_name = self.category_repository.get_by_name(db, rec_name.strip())
                if matched_by_name:
                    matched_cat_id = matched_by_name.id

        if matched_cat_id:
            product.category_id = matched_cat_id
            acc_state["category"] = "accepted"
            applied_fields.append("category_id")
        else:
            acc_state["category"] = "rejected"

        # 5. Non-canonical discovery fields (tags, keywords, attributes)
        # Stored in acceptance_state only; never in applied_fields
        for non_canon in ("tags", "keywords", "attributes"):
            if non_canon in output:
                acc_state[non_canon] = "accepted"

        # 6. Atomic Transaction: commit both Product and AIGeneration updates
        try:
            self.product_repository.update(db, product, commit=False)
            generation.acceptance_state = acc_state
            self.ai_generation_repository.update(db, generation, commit=False)
            if self.embedding_service:
                self.embedding_service.invalidate_embedding(db, product.id, commit=False)
            db.commit()
            db.refresh(product)
            db.refresh(generation)
        except Exception:
            db.rollback()
            raise

        if self.embedding_service and background_tasks is not None:
            try:
                from app.services.embedding_service import run_async_product_embedding
                _, expected_hash = self.embedding_service.build_embedding_document(db, product)
                background_tasks.add_task(
                    run_async_product_embedding,
                    product.id,
                    expected_hash
                )
            except Exception:
                pass

        return AIAcceptanceResponse(
            product_id=product.id,
            generation_id=generation.id,
            acceptance_state=acc_state,
            applied_fields=applied_fields,
            product=self._product_to_dict(product)
        )

    def review_selected(
        self,
        db: Session,
        product_id: int,
        decisions: dict[str, FieldReviewDecision],
        background_tasks: Optional[Any] = None
    ) -> AIAcceptanceResponse:
        """Applies granular field-level seller review decisions to the active generation.

        Supports:
        - accept: copies AI output value to canonical field.
        - modify: validates seller-supplied override value and applies it.
        - reject: preserves existing product value; marks field rejected.
        - pending: preserves existing product value; marks field pending.

        Non-canonical fields (tags, keywords, attributes) may be accepted, modified,
        or rejected in acceptance_state, but will NEVER appear in applied_fields.

        Args:
            db: Active SQLAlchemy database session.
            product_id: Primary key of the product.
            decisions: Mapping of field names to FieldReviewDecision objects.

        Returns:
            AIAcceptanceResponse summarizing applied fields and updated state.
        """
        product = self.product_repository.get_by_id(db, product_id)
        if not product:
            raise ProductNotFoundError(f"Product with id {product_id} not found.")

        generation = self.get_active_generation(db, product_id)
        output = generation.output or {}
        acc_state = dict(generation.acceptance_state or {})
        applied_fields: list[str] = []

        valid_fields = {"title", "description", "brand", "category", "tags", "keywords", "attributes"}

        # Validate decision field names upfront
        for field_name in decisions.keys():
            if field_name not in valid_fields:
                raise AcceptanceValidationError(f"Invalid field name '{field_name}' in review decisions.")

        # Process each review decision
        for field, decision in decisions.items():
            action = decision.action

            if action == FieldReviewAction.ACCEPT:
                if field == "title":
                    val = (output.get("title") or {}).get("value")
                    if not val or not isinstance(val, str) or not val.strip():
                        raise AcceptanceValidationError("Cannot accept AI title: generated value is empty.")
                    product.title = val.strip()[:255]
                    acc_state["title"] = "accepted"
                    applied_fields.append("title")

                elif field == "description":
                    val = (output.get("description") or {}).get("value")
                    product.description = val[:1000] if isinstance(val, str) else None
                    acc_state["description"] = "accepted"
                    applied_fields.append("description")

                elif field == "brand":
                    val = (output.get("brand") or {}).get("value")
                    product.brand = val[:100] if isinstance(val, str) else None
                    acc_state["brand"] = "accepted"
                    applied_fields.append("brand")

                elif field == "category":
                    cat_node = output.get("category") or {}
                    cat_val = cat_node.get("value") or {}
                    rec_id = cat_val.get("recommended_category_id")
                    if rec_id is None or not isinstance(rec_id, int):
                        raise AcceptanceValidationError(
                            "Cannot accept AI category recommendation: no existing category ID provided."
                        )
                    cat = self.category_repository.get_by_id(db, rec_id)
                    if not cat:
                        raise AcceptanceValidationError(
                            f"Cannot accept AI category: recommended category ID {rec_id} not found in taxonomy."
                        )
                    product.category_id = rec_id
                    acc_state["category"] = "accepted"
                    applied_fields.append("category_id")

                elif field in ("tags", "keywords", "attributes"):
                    # Non-canonical: update acceptance_state only, NOT applied_fields
                    acc_state[field] = "accepted"

            elif action == FieldReviewAction.MODIFY:
                if decision.modified_value is None:
                    raise AcceptanceValidationError(
                        f"modified_value is mandatory when action is 'modify' for field '{field}'."
                    )
                validated_val = self._validate_field_modification(db, field, decision.modified_value)

                if field == "title":
                    product.title = validated_val
                    acc_state["title"] = "modified"
                    applied_fields.append("title")

                elif field == "description":
                    product.description = validated_val
                    acc_state["description"] = "modified"
                    applied_fields.append("description")

                elif field == "brand":
                    product.brand = validated_val
                    acc_state["brand"] = "modified"
                    applied_fields.append("brand")

                elif field == "category":
                    product.category_id = validated_val
                    acc_state["category"] = "modified"
                    applied_fields.append("category_id")

                elif field in ("tags", "keywords", "attributes"):
                    # Non-canonical: update acceptance_state only, NOT applied_fields
                    acc_state[field] = "modified"

            elif action == FieldReviewAction.REJECT:
                # Do NOT touch canonical Product field; record rejection in state
                acc_state[field] = "rejected"

            elif action == FieldReviewAction.PENDING:
                # Leave unreviewed
                acc_state[field] = "pending"

        # Check if any semantic field was accepted or modified
        has_semantic_accept_or_modify = any(
            dec.action in (FieldReviewAction.ACCEPT, FieldReviewAction.MODIFY)
            for dec in decisions.values()
        )

        # Atomic Transaction: persist Product and AIGeneration updates together
        try:
            self.product_repository.update(db, product, commit=False)
            generation.acceptance_state = acc_state
            self.ai_generation_repository.update(db, generation, commit=False)
            if has_semantic_accept_or_modify and self.embedding_service:
                self.embedding_service.invalidate_embedding(db, product.id, commit=False)
            db.commit()
            db.refresh(product)
            db.refresh(generation)
        except Exception:
            db.rollback()
            raise

        if has_semantic_accept_or_modify and self.embedding_service and background_tasks is not None:
            try:
                from app.services.embedding_service import run_async_product_embedding
                _, expected_hash = self.embedding_service.build_embedding_document(db, product)
                background_tasks.add_task(
                    run_async_product_embedding,
                    product.id,
                    expected_hash
                )
            except Exception:
                pass

        return AIAcceptanceResponse(
            product_id=product.id,
            generation_id=generation.id,
            acceptance_state=acc_state,
            applied_fields=applied_fields,
            product=self._product_to_dict(product)
        )

    def on_manual_product_update(
        self,
        db: Session,
        product_id: int,
        updated_fields: list[str]
    ) -> None:
        """Hook called when a seller manually edits a Product via standard catalog APIs.

        If a field being updated was previously marked 'accepted' in the active AI
        generation's acceptance_state, its status transitions to 'modified'.

        Coordinates with the caller's ongoing transaction without calling commit.

        Args:
            db: Active SQLAlchemy database session.
            product_id: Primary key of the product being updated.
            updated_fields: List of field names updated by the seller (e.g. ['title', 'price']).
        """
        meta = self.product_metadata_repository.get_by_product_id(db, product_id)
        if not meta or not meta.current_generation_id:
            return

        generation = self.ai_generation_repository.get_by_id(db, meta.current_generation_id)
        if not generation or not generation.acceptance_state:
            return

        acc_state = dict(generation.acceptance_state)
        state_changed = False

        # Map Product model field names to acceptance_state keys
        for field in updated_fields:
            mapped_key = "category" if field == "category_id" else field
            if acc_state.get(mapped_key) == "accepted":
                acc_state[mapped_key] = "modified"
                state_changed = True

        if state_changed:
            generation.acceptance_state = acc_state
            # Stage update without committing so caller's transaction coordinates it
            self.ai_generation_repository.update(db, generation, commit=False)

    def _validate_field_modification(
        self,
        db: Session,
        field: str,
        value: Any
    ) -> Any:
        """Performs strict field-specific business and type validation for seller overrides."""
        if field == "title":
            if not isinstance(value, str) or not value.strip():
                raise AcceptanceValidationError("Title modified_value must be a non-empty string.")
            stripped = value.strip()
            if len(stripped) > 255:
                raise AcceptanceValidationError(
                    f"Title exceeds maximum length of 255 characters (length: {len(stripped)})."
                )
            return stripped

        elif field == "description":
            if value is not None and not isinstance(value, str):
                raise AcceptanceValidationError("Description modified_value must be a string or null.")
            if value and len(value) > 1000:
                raise AcceptanceValidationError(
                    f"Description exceeds maximum length of 1000 characters (length: {len(value)})."
                )
            return value

        elif field == "brand":
            if value is not None and not isinstance(value, str):
                raise AcceptanceValidationError("Brand modified_value must be a string or null.")
            if value and len(value) > 100:
                raise AcceptanceValidationError(
                    f"Brand exceeds maximum length of 100 characters (length: {len(value)})."
                )
            return value

        elif field == "category":
            try:
                cat_id = int(value)
            except (ValueError, TypeError):
                raise AcceptanceValidationError(
                    f"Category modified_value must be an integer category ID, got: {value}"
                )
            category = self.category_repository.get_by_id(db, cat_id)
            if not category:
                raise AcceptanceValidationError(f"Category with ID {cat_id} does not exist.")
            return cat_id

        elif field in ("tags", "keywords"):
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                raise AcceptanceValidationError(f"{field} modified_value must be a list of strings.")
            return value

        elif field == "attributes":
            if not isinstance(value, dict):
                raise AcceptanceValidationError("attributes modified_value must be a dictionary.")
            return value

        else:
            raise AcceptanceValidationError(f"Unsupported field for modification: '{field}'")

    @staticmethod
    def _product_to_dict(product: Product) -> dict[str, Any]:
        """Serializes canonical Product entity to a clean dictionary representation."""
        return {
            "id": product.id,
            "title": product.title,
            "description": product.description,
            "brand": product.brand,
            "sku": product.sku,
            "price": product.price,
            "status": product.status,
            "category_id": product.category_id,
            "created_at": product.created_at.isoformat() if product.created_at else None,
            "updated_at": product.updated_at.isoformat() if product.updated_at else None,
        }
