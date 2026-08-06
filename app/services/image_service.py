from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.image import Image
from app.repositories.image_repository import ImageRepository
from app.repositories.product_repository import ProductRepository
from app.utils.file_storage import FileStorageService


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