from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.product import Product
from app.schemas.product import ProductCreate

class ProductRepository:
    def create(
        self,
        db: Session,
        product: ProductCreate
    ) -> Product:

        db_product = Product(**product.model_dump())

        db.add(db_product)
        db.commit()
        db.refresh(db_product)

        return db_product
    
    def update(
        self,
        db: Session,
        product: Product,
        commit: bool = True
    ) -> Product:

        if commit:
            db.commit()
            db.refresh(product)

        return product
    
    def delete(
        self,
        db: Session,
        product: Product
    ) -> None:

        db.delete(product)
        db.commit()
    
    def get_by_id(
        self,
        db: Session,
        product_id: int
    ) -> Product | None:

        return (
            db.query(Product)
            .filter(Product.id == product_id)
            .first()
        )
    
    def get_all(
        self,
        db: Session
    ) -> list[Product]:

        return db.query(Product).all()
    
    def get_by_sku(
        self,
        db: Session,
        sku: str
    ) -> Product | None:

        return (
            db.query(Product)
            .filter(Product.sku == sku)
            .first()
        )
        
    def get_by_category(
        self,
        db: Session,
        category_id: int
    ) -> list[Product]:

        return (
            db.query(Product)
            .filter(Product.category_id == category_id)
            .all()
        )
    
    def search(
        self,
        db: Session,
        keyword: str
    ) -> list[Product]:

        return (
            db.query(Product)
            .filter(
                or_(
                    Product.title.ilike(f"%{keyword}%"),
                    Product.description.ilike(f"%{keyword}%"),
                    Product.brand.ilike(f"%{keyword}%")
                )
            )
            .all()
        )
        
