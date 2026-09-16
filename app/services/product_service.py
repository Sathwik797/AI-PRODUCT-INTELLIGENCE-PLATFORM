from typing import Any, Optional
from sqlalchemy.orm import Session

from app.models.product import Product
from app.repositories.category_repository import CategoryRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.ai_acceptance_service import AIAcceptanceService


class ProductService:

    def __init__(
        self,
        product_repository: ProductRepository,
        category_repository: CategoryRepository,
        ai_acceptance_service: AIAcceptanceService,
        embedding_service: Optional[Any] = None,
    ):
        self.product_repository = product_repository
        self.category_repository = category_repository
        self.ai_acceptance_service = ai_acceptance_service
        self.embedding_service = embedding_service
    
    def create(
        self,
        db: Session,
        product: ProductCreate
    ) -> Product:

        existing_product = self.product_repository.get_by_sku(
            db,
            product.sku
        )

        if existing_product:
            raise ValueError("Product with this SKU already exists.")

        category = self.category_repository.get_by_id(
            db,
            product.category_id
        )

        if not category:
            raise ValueError("Category not found.")

        return self.product_repository.create(
            db,
            product
        )
        
    def get_all(
        self,
        db: Session
    ) -> list[Product]:

        return self.product_repository.get_all(db)
    
    def get_by_id(
        self,
        db: Session,
        product_id: int
    ) -> Product:

        product = self.product_repository.get_by_id(
            db,
            product_id
        )

        if not product:
            raise ValueError("Product not found.")

        return product
    
    def get_by_category(
        self,
        db: Session,
        category_id: int
    ) -> list[Product]:

        category = self.category_repository.get_by_id(
            db,
            category_id
        )

        if not category:
            raise ValueError("Category not found.")

        return self.product_repository.get_by_category(
            db,
            category_id
        )
    
    def search(
        self,
        db: Session,
        keyword: str
    ) -> list[Product]:

        return self.product_repository.search(
            db,
            keyword
        )
    
    def update(
        self,
        db: Session,
        product_id: int,
        product_update: ProductUpdate,
        background_tasks: Optional[Any] = None
    ) -> Product:

        # Check if product exists
        product = self.get_by_id(db, product_id)

        # Get only the fields provided by the client
        update_data = product_update.model_dump(exclude_unset=True)

        # Check if SKU is being updated
        if "sku" in update_data:
            existing_product = self.product_repository.get_by_sku(
                db,
                update_data["sku"]
            )

            if existing_product is not None:
                if existing_product.id != product.id:
                    raise ValueError("Product with this SKU already exists.")
                
        # Check if category is being updated
        if "category_id" in update_data:
            category = self.category_repository.get_by_id(
                db,
                update_data["category_id"]
            )

            if not category:
                raise ValueError("Category not found.")

        # Update only the provided fields
        for field, value in update_data.items():
            setattr(product, field, value)

        # Synchronize manual seller edits with active AI metadata acceptance state
        self.ai_acceptance_service.on_manual_product_update(
            db=db,
            product_id=product.id,
            updated_fields=list(update_data.keys())
        )

        # Invalidate embedding if semantic fields changed (Q43)
        semantic_changed = any(
            f in update_data
            for f in ("title", "description", "brand", "category_id")
        )
        if semantic_changed and self.embedding_service:
            self.embedding_service.invalidate_embedding(db, product.id, commit=False)

        # Save changes
        saved_product = self.product_repository.update(
            db,
            product
        )

        # Enqueue async embedding generation if semantic fields changed
        if semantic_changed and self.embedding_service and background_tasks is not None:
            try:
                from app.services.embedding_service import run_async_product_embedding
                _, expected_hash = self.embedding_service.build_embedding_document(db, saved_product)
                background_tasks.add_task(
                    run_async_product_embedding,
                    saved_product.id,
                    expected_hash
                )
            except Exception:
                pass

        return saved_product
        
    def delete(
        self,
        db: Session,
        product_id: int
    ) -> None:

        product = self.get_by_id(
            db,
            product_id
        )

        self.product_repository.delete(
            db,
            product
        )