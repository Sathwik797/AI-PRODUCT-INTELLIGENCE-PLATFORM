from sqlalchemy.orm import Session

from app.models.image import Image


class ImageRepository:

    def create(
        self,
        db: Session,
        image: Image
    ) -> Image:

        db.add(image)
        db.commit()
        db.refresh(image)

        return image

    def get_by_id(
        self,
        db: Session,
        image_id: int
    ) -> Image | None:

        return (
            db.query(Image)
            .filter(Image.id == image_id)
            .first()
        )

    def get_by_product(
        self,
        db: Session,
        product_id: int
    ) -> list[Image]:

        return (
            db.query(Image)
            .filter(Image.product_id == product_id)
            .order_by(Image.display_order)
            .all()
        )

    def update(
        self,
        db: Session,
        image: Image
    ) -> Image:

        db.commit()
        db.refresh(image)

        return image

    def delete(
        self,
        db: Session,
        image: Image
    ) -> None:

        db.delete(image)
        db.commit()