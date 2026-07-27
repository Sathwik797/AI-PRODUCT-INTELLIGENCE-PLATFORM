# app/models/product.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String(255), nullable=False)

    description = Column(String(1000), nullable=True)

    brand = Column(String(100), nullable=True)

    sku = Column(String(100), unique=True, nullable=False)

    price = Column(Float, nullable=False)

    status = Column(
        String(20),
        default="ACTIVE",
        nullable=False
    )

    category_id = Column(
        Integer,
        ForeignKey("categories.id"),
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    category = relationship(
        "Category",
        back_populates="products"
    )