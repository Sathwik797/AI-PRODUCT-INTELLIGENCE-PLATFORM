from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import db
from app.repositories.category_repository import CategoryRepository
from app.schemas.category import CategoryCreate
from app.schemas.category import CategoryUpdate


class CategoryService:

    def __init__(self):
        self.repository = CategoryRepository()

    def create_category(
        self,
        db: Session,
        category: CategoryCreate
    ):

        existing_category = self.repository.get_by_name(
            db,
            category.name
        )

        if existing_category:
            raise HTTPException(
                status_code=409,
                detail="Category already exists."
            )

        return self.repository.create(db, category)
    
    def update_category(
        self,
        db: Session,
        category_id: int,
        update: CategoryUpdate
    ):
        category = self.repository.get_by_id(
            db,
            category_id
        )

        if not category:
            raise HTTPException(
                status_code=404,
                detail="Category not found."
            )

        existing = self.repository.get_by_name(
            db,
            update.name
        )

        if existing and existing.id != category.id:
            raise HTTPException(
                status_code=409,
                detail="Category already exists."
            )

        category.name = update.name

        return self.repository.update(
            db,
            category
        )
    
    def delete_category(
        self,
        db: Session,
        category_id: int
    ):
        category = self.repository.get_by_id(
            db,
            category_id
        )

        if not category:
            raise HTTPException(
                status_code=404,
                detail="Category not found."
            )

        self.repository.delete(
            db,
            category
        )
    
    def get_all_categories(self, db: Session):
        return self.repository.get_all(db)
    
    def get_category_by_id(
        self,
        db: Session,
        category_id: int
    ):
        category = self.repository.get_by_id(
            db,
            category_id
        )

        if not category:
            raise HTTPException(
                status_code=404,
                detail="Category not found."
            )

        return category