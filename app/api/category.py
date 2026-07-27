from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session


from app.db.dependencies import get_db
from app.schemas.category import CategoryCreate, CategoryResponse
from app.services.category_service import CategoryService
from app.schemas.category import (
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
)

router = APIRouter(
    prefix="/categories",
    tags=["Categories"]
)

service = CategoryService()


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=201
)
def create_category(
    category: CategoryCreate,
    db: Session = Depends(get_db)
):
    return service.create_category(db, category)



@router.put(
    "/{category_id}",
    response_model=CategoryResponse
)
def update_category(
    category_id: int,
    update: CategoryUpdate,
    db: Session = Depends(get_db)
):
    return service.update_category(
        db,
        category_id,
        update
    )
    
@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db)
):
    service.delete_category(
        db,
        category_id
    )

    
@router.get(
    "",
    response_model=list[CategoryResponse]
)
def get_all_categories(
    db: Session = Depends(get_db)
):
    return service.get_all_categories(db)

@router.get(
    "/{category_id}",
    response_model=CategoryResponse
)


def get_category_by_id(
    category_id: int,
    db: Session = Depends(get_db)
):
    return service.get_category_by_id(
        db,
        category_id
    )