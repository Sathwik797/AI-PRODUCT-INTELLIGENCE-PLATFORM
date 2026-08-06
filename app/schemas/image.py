from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImageResponse(BaseModel):

    id: int

    product_id: int

    image_url: str

    filename: str

    mime_type: str

    file_size: int

    width: int

    height: int

    display_order: int

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )