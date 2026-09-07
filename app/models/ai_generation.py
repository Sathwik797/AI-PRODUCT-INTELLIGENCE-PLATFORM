from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    JSON,
    ForeignKey,
    DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class AIGeneration(Base):
    __tablename__ = "ai_generations"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False,
        index=True
    )

    generation_number = Column(
        Integer,
        nullable=False
    )

    status = Column(
        String(50),
        nullable=False
    )

    output = Column(
        JSON,
        nullable=True
    )

    acceptance_state = Column(
        JSON,
        nullable=True
    )

    model_name = Column(
        String(100),
        nullable=True
    )

    model_version = Column(
        String(50),
        nullable=True
    )

    prompt_version = Column(
        String(50),
        nullable=True
    )

    schema_version = Column(
        String(50),
        nullable=True
    )

    processing_time = Column(
        Float,
        nullable=True
    )

    error_message = Column(
        Text,
        nullable=True
    )

    started_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    completed_at = Column(
        DateTime(timezone=True),
        nullable=True
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
        back_populates="ai_generations"
    )
