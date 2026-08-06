from pathlib import Path
from uuid import uuid4
import shutil
from PIL import Image
import mimetypes

from fastapi import UploadFile


class FileStorageService:

    UPLOAD_DIR = Path("uploads/products")

    def create_product_folder(
        self,
        product_id: int
    ) -> Path:

        product_folder = (
            self.UPLOAD_DIR
            / str(product_id)
        )

        product_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        return product_folder

    def generate_unique_filename(
        self,
        filename: str
    ) -> str:

        extension = (
            Path(filename)
            .suffix
        )

        return f"{uuid4()}{extension}"

    def save_file(
        self,
        file: UploadFile,
        product_id: int
    ) -> Path:

        product_folder = self.create_product_folder(
            product_id
        )

        if not file.filename:
            raise ValueError("Filename is missing.")

        unique_filename = (
            self.generate_unique_filename(
                file.filename
            )
        )

        file_path = (
            product_folder
            / unique_filename
        )

        with open(
            file_path,
            "wb"
        ) as buffer:

            shutil.copyfileobj(
                file.file,
                buffer
            )

        return file_path
    
    def delete_file(
        self,
        file_path: Path
    ) -> None:

        if file_path.exists():
            file_path.unlink()

    
    def get_image_metadata(
        self,
        file_path: Path
    ) -> dict:

        with Image.open(file_path) as image:

            width, height = image.size

        mime_type, _ = mimetypes.guess_type(
            str(file_path)
        )

        return {
            "width": width,
            "height": height,
            "mime_type": mime_type or "application/octet-stream",
            "file_size": file_path.stat().st_size
        }