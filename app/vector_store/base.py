"""Vector Store Abstract Boundary Port.

Phase 06: Implements Q39.
Decouples vector index storage from domain services so FAISS can later be swapped
for a dedicated vector database without domain rewrites.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class VectorStoreError(Exception):
    """Base exception for all vector store operations."""
    pass


class VectorStore(ABC):
    """Abstract interface for dense vector storage and similarity retrieval."""

    @abstractmethod
    def add_vector(self, vector_id: int, vector: list[float] | Any) -> None:
        """Adds or updates a normalized vector associated with a position-independent vector_id."""
        pass

    @abstractmethod
    def remove_vector(self, vector_id: int) -> None:
        """Removes the vector with the given vector_id from the store."""
        pass

    @abstractmethod
    def get_vector(self, vector_id: int) -> Optional[Any]:
        """Retrieves the stored vector for a given vector_id, or None if missing."""
        pass

    @abstractmethod
    def contains(self, vector_id: int) -> bool:
        """Returns True if the vector_id exists in the store."""
        pass

    @abstractmethod
    def search(self, query_vector: Any, top_k: int = 10) -> list[tuple[int, float]]:
        """Searches for nearest vectors, returning sorted list of (vector_id, similarity_score)."""
        pass

    @abstractmethod
    def count(self) -> int:
        """Returns the total number of indexed vectors."""
        pass

    @abstractmethod
    def list_vector_ids(self) -> list[int]:
        """Returns a list of all vector_ids currently present in the store."""
        pass

    @abstractmethod
    def save(self) -> None:
        """Persists the in-memory index state to disk."""
        pass

    @abstractmethod
    def load(self) -> None:
        """Loads index state from disk if present."""
        pass

    @abstractmethod
    def rebuild(self, vectors: list[tuple[int, Any]]) -> None:
        """Atomically rebuilds the index from an authoritative list of (vector_id, vector) tuples."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Removes all vectors and resets the index."""
        pass
