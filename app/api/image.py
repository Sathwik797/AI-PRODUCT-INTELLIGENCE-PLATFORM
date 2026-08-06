from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status
)
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.repositories.image_repository import ImageRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.image import ImageResponse
from app.services.image_service import ImageService
from app.utils.file_storage import FileStorageService


router = APIRouter(
    tags=["Images"]
)

image_repository = ImageRepository()

product_repository = ProductRepository()

file_storage = FileStorageService()

service = ImageService(
    image_repository,
    product_repository,
    file_storage
)


@router.post(
    "/products/{product_id}/images",
    response_model=ImageResponse,
    status_code=status.HTTP_201_CREATED
)
def upload_image(
    product_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):

    try:

        return service.upload(
            db,
            product_id,
            file
        )

    except ValueError as e:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )