from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class ProductEmbedding(Base):
    """Relational authoritative record for product embedding metadata & lifecycle state.

    Phase 06: Vector lifecycle and synchronization metadata.
    MySQL is the system of record; FAISS is a disposable, rebuildable vector projection.
    """
    __tablename__ = "product_embeddings"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )

    vector_id = Column(
        BigInteger,
        nullable=False,
        unique=True,
        index=True
    )

    content_hash = Column(
        String(64),
        nullable=False,
        index=True
    )

    embedding_model = Column(
        String(100),
        nullable=False
    )

    embedding_dimension = Column(
        Integer,
        nullable=False
    )

    builder_version = Column(
        String(50),
        nullable=False
    )

    status = Column(
        String(50),
        nullable=False,
        default="PENDING"
    )

    error_message = Column(
        Text,
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
        back_populates="embedding"
    )
