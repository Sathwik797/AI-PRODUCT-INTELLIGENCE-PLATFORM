from sqlalchemy.orm import Session

from app.models.product_metadata import ProductMetadata


class ProductMetadataRepository:
    """Repository for ProductMetadata singleton active pointer records."""

    def get_by_product_id(
        self,
        db: Session,
        product_id: int
    ) -> ProductMetadata | None:
        return (
            db.query(ProductMetadata)
            .filter(ProductMetadata.product_id == product_id)
            .first()
        )

    def create(
        self,
        db: Session,
        metadata: ProductMetadata,
        commit: bool = True
    ) -> ProductMetadata:
        db.add(metadata)
        if commit:
            db.commit()
            db.refresh(metadata)
        return metadata

    def update(
        self,
        db: Session,
        metadata: ProductMetadata,
        commit: bool = True
    ) -> ProductMetadata:
        if commit:
            db.commit()
            db.refresh(metadata)
        return metadata

    def set_current_generation(
        self,
        db: Session,
        product_id: int,
        generation_id: int,
        commit: bool = True
    ) -> ProductMetadata:
        """Sets or creates the active generation pointer for a product.

        Supports commit=False so that callers can coordinate the final success
        commit with other entities within the same database transaction.
        """
        metadata = self.get_by_product_id(db, product_id)
        if metadata:
            metadata.current_generation_id = generation_id
            if commit:
                db.commit()
                db.refresh(metadata)
            return metadata

        new_metadata = ProductMetadata(
            product_id=product_id,
            current_generation_id=generation_id
        )
        db.add(new_metadata)
        if commit:
            db.commit()
            db.refresh(new_metadata)
        return new_metadata
