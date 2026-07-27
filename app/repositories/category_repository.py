from sqlalchemy.orm import Session

from app.models.category import Category
from app.schemas.category import CategoryCreate


class CategoryRepository:

    def create(self, db: Session, category: CategoryCreate) -> Category:
        db_category = Category(
            name=category.name
        )

        db.add(db_category)
        db.commit()
        db.refresh(db_category)

        return db_category
    
    def update(
        self,
        db: Session,
        category: Category
    ) -> Category:

        db.commit()
        db.refresh(category)

        return category
    
    def delete(
        self,
        db: Session,
        category: Category
    ) -> None:
        db.delete(category)
        db.commit()
    
    def get_by_name(self, db: Session, name: str) -> Category | None:
        return (
            db.query(Category)
            .filter(Category.name == name)
            .first()
        )
    
    def get_all(self, db: Session) -> list[Category]:
        return db.query(Category).all()
    
    def get_by_id(self, db: Session, category_id: int) -> Category | None:
        return (
            db.query(Category)
            .filter(Category.id == category_id)
            .first()
        )