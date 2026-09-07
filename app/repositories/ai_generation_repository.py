from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ai_generation import AIGeneration


class AIGenerationRepository:
    """Repository for AIGeneration domain entities."""

    def create(
        self,
        db: Session,
        generation: AIGeneration,
        commit: bool = True
    ) -> AIGeneration:
        db.add(generation)
        if commit:
            db.commit()
            db.refresh(generation)
        return generation

    def get_by_id(
        self,
        db: Session,
        generation_id: int
    ) -> AIGeneration | None:
        return (
            db.query(AIGeneration)
            .filter(AIGeneration.id == generation_id)
            .first()
        )

    def get_latest_for_product(
        self,
        db: Session,
        product_id: int
    ) -> AIGeneration | None:
        return (
            db.query(AIGeneration)
            .filter(AIGeneration.product_id == product_id)
            .order_by(AIGeneration.generation_number.desc())
            .first()
        )

    def get_by_product(
        self,
        db: Session,
        product_id: int
    ) -> list[AIGeneration]:
        return (
            db.query(AIGeneration)
            .filter(AIGeneration.product_id == product_id)
            .order_by(AIGeneration.generation_number.asc())
            .all()
        )

    def get_next_generation_number(
        self,
        db: Session,
        product_id: int
    ) -> int:
        """Calculates next monotonically increasing generation number for a product.

        Uses MAX(generation_number) + 1 from persisted generation history.

        TODO: Concurrency-Protection Architectural Concern:
        In high-concurrency or multi-worker production deployments, this
        read-then-increment approach is not concurrency-safe without database-level
        locking (e.g., SELECT ... FOR UPDATE), optimistic locking, or a database
        UNIQUE constraint on (product_id, generation_number). For single-worker /
        standard transactional workflows, MAX + 1 provides proper sequencing across
        completed and failed generations.
        """
        max_gen = (
            db.query(func.max(AIGeneration.generation_number))
            .filter(AIGeneration.product_id == product_id)
            .scalar()
        )
        return (max_gen or 0) + 1

    def update(
        self,
        db: Session,
        generation: AIGeneration,
        commit: bool = True
    ) -> AIGeneration:
        if commit:
            db.commit()
            db.refresh(generation)
        return generation
