from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.image import Image
from app.repositories.image_repository import ImageRepository
from app.repositories.product_repository import ProductRepository
from app.utils.file_storage import FileStorageService
from pathlib import Path

class ImageService:

    def __init__(
        self,
        image_repository: ImageRepository,
        product_repository: ProductRepository,
        file_storage: FileStorageService
    ):
        self.image_repository = image_repository
        self.product_repository = product_repository
        self.file_storage = file_storage
        
    def upload(
        self,
        db: Session,
        product_id: int,
        file: UploadFile
    ) -> Image:

        # Check if product exists
        product = self.product_repository.get_by_id(
            db,
            product_id
        )

        if not product:
            raise ValueError("Product not found.")
        
        self.file_storage.validate_file(
            file
        )

        file_path = None

        try:

            # Save physical file
            file_path = self.file_storage.save_file(
                file,
                product_id
            )

            # Extract metadata
            metadata = self.file_storage.get_image_metadata(
                file_path
            )

            # Determine display order
            existing_images = (
                self.image_repository.get_by_product(
                    db,
                    product_id
                )
            )

            display_order = (
                len(existing_images) + 1
            )

            # Create ORM object
            image = Image(
                product_id=product_id,
                image_url=str(file_path),
                filename=file_path.name,
                mime_type=metadata["mime_type"],
                file_size=metadata["file_size"],
                width=metadata["width"],
                height=metadata["height"],
                display_order=display_order
            )

            return self.image_repository.create(
                db,
                image
            )

        except Exception:
            # Rollback the uploaded file
            if file_path is not None:
                self.file_storage.delete_file(
                    file_path
                )

            raise
    
    def get_by_product(
        self,
        db: Session,
        product_id: int
    ) -> list[Image]:

        product = self.product_repository.get_by_id(
            db,
            product_id
        )

        if not product:
            raise ValueError(
                "Product not found."
            )

        return self.image_repository.get_by_product(
            db,
            product_id
        )
    
    def delete(
        self,
        db: Session,
        image_id: int
    ) -> None:

        image = self.image_repository.get_by_id(
            db,
            image_id
        )
        if not image:
            raise ValueError(
                "Image not found."
            )

        file_path = Path(
            str(image.image_url)
        )

        # Delete database record first
        self.image_repository.delete(
            db,
            image
        )

        # Best effort filesystem cleanup
        self.file_storage.delete_file(
            file_path
        )
    
    def update_display_order(
        self,
        db: Session,
        image_id: int,
        new_position: int
    ) -> Image:

        image = self.image_repository.get_by_id(
            db,
            image_id
        )

        if not image:
            raise ValueError(
                "Image not found."
            )

        images = self.image_repository.get_by_product(
            db,
            image.product_id
        )

        if (
            new_position < 1
            or
            new_position > len(images)
        ):
            raise ValueError(
                f"Display order must be between 1 and {len(images)}."
            )

        images.remove(image)

        images.insert(
            new_position - 1,
            image
        )

        for index, img in enumerate(images):

            img.display_order = index + 1

        db.commit()

        db.refresh(image)

        return image