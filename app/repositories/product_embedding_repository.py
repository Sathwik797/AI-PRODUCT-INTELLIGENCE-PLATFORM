from typing import Optional
from sqlalchemy.orm import Session

from app.models.product_embedding import ProductEmbedding


class ProductEmbeddingRepository:
    """Repository for ProductEmbedding entity persistence and query operations."""

    def get_by_product_id(
        self,
        db: Session,
        product_id: int
    ) -> Optional[ProductEmbedding]:
        return (
            db.query(ProductEmbedding)
            .filter(ProductEmbedding.product_id == product_id)
            .first()
        )

    def get_by_vector_id(
        self,
        db: Session,
        vector_id: int
    ) -> Optional[ProductEmbedding]:
        return (
            db.query(ProductEmbedding)
            .filter(ProductEmbedding.vector_id == vector_id)
            .first()
        )

    def create(
        self,
        db: Session,
        embedding: ProductEmbedding,
        commit: bool = True
    ) -> ProductEmbedding:
        db.add(embedding)
        if commit:
            db.commit()
            db.refresh(embedding)
        return embedding

    def update(
        self,
        db: Session,
        embedding: ProductEmbedding,
        commit: bool = True
    ) -> ProductEmbedding:
        if commit:
            db.commit()
            db.refresh(embedding)
        return embedding

    def delete(
        self,
        db: Session,
        embedding: ProductEmbedding,
        commit: bool = True
    ) -> None:
        db.delete(embedding)
        if commit:
            db.commit()

    def list_all_ready(
        self,
        db: Session
    ) -> list[ProductEmbedding]:
        return (
            db.query(ProductEmbedding)
            .filter(ProductEmbedding.status == "READY")
            .all()
        )

    def list_all(
        self,
        db: Session
    ) -> list[ProductEmbedding]:
        return db.query(ProductEmbedding).all()
