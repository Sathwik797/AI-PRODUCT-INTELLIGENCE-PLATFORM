from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Category name"
    )

class CategoryUpdate(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Updated category name"
    )


class CategoryResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)