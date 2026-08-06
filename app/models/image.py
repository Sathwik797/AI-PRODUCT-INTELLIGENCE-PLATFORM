from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Image(Base):
    __tablename__ = "images"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False
    )

    image_url = Column(
        String(500),
        nullable=False
    )

    filename = Column(
        String(255),
        nullable=False
    )

    mime_type = Column(
        String(100),
        nullable=False
    )

    file_size = Column(
        Integer,
        nullable=False
    )

    width = Column(
        Integer,
        nullable=False
    )

    height = Column(
        Integer,
        nullable=False
    )

    display_order = Column(
        Integer,
        default=1,
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

    product = relationship(
        "Product",
        back_populates="images"
    )