from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.dependencies import get_db

from app.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
)

from app.repositories.product_repository import ProductRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.ai_generation_repository import AIGenerationRepository
from app.repositories.product_metadata_repository import ProductMetadataRepository
from app.services.ai_acceptance_service import AIAcceptanceService
from app.services.product_service import ProductService


router = APIRouter(
    prefix="/products",
    tags=["Products"]
)

product_repository = ProductRepository()
category_repository = CategoryRepository()
ai_generation_repository = AIGenerationRepository()
product_metadata_repository = ProductMetadataRepository()

ai_acceptance_service = AIAcceptanceService(
    product_repository=product_repository,
    ai_generation_repository=ai_generation_repository,
    product_metadata_repository=product_metadata_repository,
    category_repository=category_repository,
)

service = ProductService(
    product_repository=product_repository,
    category_repository=category_repository,
    ai_acceptance_service=ai_acceptance_service,
)

@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED
)
def create_product(
    product: ProductCreate,
    db: Session = Depends(get_db)
):
    return service.create(
        db,
        product
    )

@router.get(
    "",
    response_model=list[ProductResponse]
)
def get_all_products(
    db: Session = Depends(get_db)
):
    return service.get_all(db)

@router.get(
    "/{product_id}",
    response_model=ProductResponse
)
def get_product_by_id(
    product_id: int,
    db: Session = Depends(get_db)
):
    return service.get_by_id(
        db,
        product_id
    )

@router.get(
    "/category/{category_id}",
    response_model=list[ProductResponse]
)
def get_products_by_category(
    category_id: int,
    db: Session = Depends(get_db)
):
    return service.get_by_category(
        db,
        category_id
    )

@router.get(
    "/search/{keyword}",
    response_model=list[ProductResponse]
)
def search_products(
    keyword: str,
    db: Session = Depends(get_db)
):
    return service.search(
        db,
        keyword
    )

@router.put(
    "/{product_id}",
    response_model=ProductResponse
)
def update_product(
    product_id: int,
    update: ProductUpdate,
    db: Session = Depends(get_db)
):
    return service.update(
        db,
        product_id,
        update
    )

@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    service.delete(
        db,
        product_id
    )