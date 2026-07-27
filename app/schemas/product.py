from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ProductBase(BaseModel):
    title: str
    description: Optional[str] = None
    brand: Optional[str] = None
    sku: str
    price: float
    category_id: int
    status: str = "ACTIVE"


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    brand: Optional[str] = None
    sku: Optional[str] = None
    price: Optional[float] = None
    category_id: Optional[int] = None
    status: Optional[str] = None


class ProductResponse(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)