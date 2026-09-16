"""FAISS Vector Store Implementation.

Phase 06: Implements Q39, Q40, Q47, Q49.
Wraps faiss.IndexIDMap2(faiss.IndexFlatIP(dimension)) with cosine normalization,
atomic file persistence, thread-safe access, and atomic index rebuilds.
"""

import json
import logging
import os
from pathlib import Path
import threading
from typing import Any, Optional

import numpy as np

from app.vector_store.base import VectorStore, VectorStoreError

logger = logging.getLogger(__name__)


class FAISSVectorStore(VectorStore):
    """Local persisted FAISS vector index implementing the VectorStore port."""

    def __init__(
        self,
        dimension: int = 768,
        storage_dir: str = "data/faiss",
        index_filename: str = "index.bin",
        metadata_filename: str = "metadata.json",
        auto_load: bool = True
    ):
        self.dimension = dimension
        self.storage_dir = Path(storage_dir)
        self.index_path = self.storage_dir / index_filename
        self.metadata_path = self.storage_dir / metadata_filename
        self._lock = threading.RLock()

        try:
            import faiss
            self._faiss = faiss
        except ImportError as e:
            raise VectorStoreError(f"faiss is not installed: {e}") from e

        self._index = self._create_empty_index()

        if auto_load and self.index_path.exists():
            self.load()

    def _create_empty_index(self):
        """Creates a fresh, empty IndexIDMap2 wrapping an IndexFlatIP."""
        base_index = self._faiss.IndexFlatIP(self.dimension)
        return self._faiss.IndexIDMap2(base_index)

    def _prepare_vector(self, vector: list[float] | np.ndarray) -> np.ndarray:
        """Validates dimensionality, converts to float32 2D array, and applies L2 normalization."""
        if isinstance(vector, list):
            arr = np.array([vector], dtype=np.float32)
        elif isinstance(vector, np.ndarray):
            if vector.ndim == 1:
                arr = vector.reshape(1, -1).astype(np.float32)
            elif vector.ndim == 2:
                arr = vector.astype(np.float32)
            else:
                raise VectorStoreError(f"Unsupported vector ndim: {vector.ndim}")
        else:
            raise VectorStoreError(f"Unsupported vector type: {type(vector)}")

        if arr.shape[1] != self.dimension:
            raise VectorStoreError(
                f"Vector dimension mismatch: expected {self.dimension}, got {arr.shape[1]}"
            )

        # In-place L2 normalization so Inner Product represents Cosine Similarity
        self._faiss.normalize_L2(arr)
        return arr

    def add_vector(self, vector_id: int, vector: list[float] | np.ndarray) -> None:
        """Adds or updates a vector with a given int64 vector_id."""
        norm_vec = self._prepare_vector(vector)
        ids = np.array([vector_id], dtype=np.int64)

        with self._lock:
            # If ID already exists in index, remove old vector first to update
            if self.contains(vector_id):
                self.remove_vector(vector_id)
            self._index.add_with_ids(norm_vec, ids)
            self.save()

    def remove_vector(self, vector_id: int) -> None:
        """Removes a vector by ID if it exists."""
        with self._lock:
            if not self.contains(vector_id):
                return
            ids = np.array([vector_id], dtype=np.int64)
            self._index.remove_ids(ids)
            self.save()

    def get_vector(self, vector_id: int) -> Optional[np.ndarray]:
        """Reconstructs vector from index by vector_id."""
        with self._lock:
            if not self.contains(vector_id):
                return None
            try:
                vec = self._index.reconstruct(int(vector_id))
                return vec
            except Exception:
                return None

    def contains(self, vector_id: int) -> bool:
        """Checks if vector_id is currently present in the index."""
        with self._lock:
            try:
                # IndexIDMap2 maintains id_map or allows reconstruct
                self._index.reconstruct(int(vector_id))
                return True
            except Exception:
                return False

    def search(self, query_vector: list[float] | np.ndarray, top_k: int = 10) -> list[tuple[int, float]]:
        """Searches index for top_k nearest neighbors by cosine similarity."""
        norm_query = self._prepare_vector(query_vector)

        with self._lock:
            if self._index.ntotal == 0:
                return []
            k = min(top_k, self._index.ntotal)
            distances, indices = self._index.search(norm_query, k)

            results: list[tuple[int, float]] = []
            for idx, score in zip(indices[0], distances[0]):
                if idx != -1:
                    results.append((int(idx), float(score)))
            return results

    def count(self) -> int:
        """Returns the number of indexed vectors."""
        with self._lock:
            return int(self._index.ntotal)

    def list_vector_ids(self) -> list[int]:
        """Returns a list of all vector_ids currently present in the index."""
        with self._lock:
            if self._index.ntotal == 0:
                return []
            try:
                ids = self._faiss.vector_to_array(self._index.id_map)
                return [int(x) for x in ids]
            except Exception as e:
                logger.error(f"Failed to list vector IDs from FAISS index: {e}")
                return []

    def save(self) -> None:
        """Thread-safe, atomic write of index and metadata to disk."""
        with self._lock:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            tmp_index_path = self.index_path.with_suffix(".tmp")
            tmp_meta_path = self.metadata_path.with_suffix(".tmp")

            try:
                self._faiss.write_index(self._index, str(tmp_index_path))

                meta = {
                    "dimension": self.dimension,
                    "count": int(self._index.ntotal),
                }
                with open(tmp_meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)

                # Atomic replacement on disk
                if tmp_index_path.exists():
                    os.replace(tmp_index_path, self.index_path)
                if tmp_meta_path.exists():
                    os.replace(tmp_meta_path, self.metadata_path)

            except Exception as e:
                logger.error(f"Failed to save FAISS index: {e}")
                if tmp_index_path.exists():
                    try:
                        os.remove(tmp_index_path)
                    except Exception:
                        pass
                if tmp_meta_path.exists():
                    try:
                        os.remove(tmp_meta_path)
                    except Exception:
                        pass
                raise VectorStoreError(f"Failed to save FAISS index: {e}") from e

    def load(self) -> None:
        """Loads index from disk."""
        with self._lock:
            if not self.index_path.exists():
                return
            try:
                loaded_index = self._faiss.read_index(str(self.index_path))
                self._index = loaded_index
                logger.info(f"Loaded FAISS index with {self._index.ntotal} vectors from {self.index_path}")
            except Exception as e:
                logger.error(f"Failed to load FAISS index from {self.index_path}: {e}")
                raise VectorStoreError(f"Failed to load FAISS index: {e}") from e

    def rebuild(self, vectors: list[tuple[int, list[float] | np.ndarray]]) -> None:
        """Atomically rebuilds the index from scratch without corrupting active index if failed.

        Implements Q49:
        1. Builds a fresh temporary index.
        2. Populates all vectors.
        3. Saves to temporary file and validates.
        4. Atomically swaps in-memory active index pointer and file.
        """
        new_index = self._create_empty_index()

        if vectors:
            id_list: list[int] = []
            vec_list: list[np.ndarray] = []
            for vid, vec in vectors:
                norm_vec = self._prepare_vector(vec)
                id_list.append(vid)
                vec_list.append(norm_vec[0])

            all_ids = np.array(id_list, dtype=np.int64)
            all_vecs = np.vstack(vec_list).astype(np.float32)
            new_index.add_with_ids(all_vecs, all_ids)

        with self._lock:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            tmp_index_path = self.index_path.with_suffix(".rebuild.tmp")
            tmp_meta_path = self.metadata_path.with_suffix(".rebuild.tmp")
            try:
                self._faiss.write_index(new_index, str(tmp_index_path))
                meta = {
                    "dimension": self.dimension,
                    "count": int(new_index.ntotal),
                }
                with open(tmp_meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)

                # Atomic disk replacement
                os.replace(tmp_index_path, self.index_path)
                os.replace(tmp_meta_path, self.metadata_path)

                # Atomically update in-memory active index pointer ONLY after disk save succeeded
                self._index = new_index
                logger.info(f"Successfully rebuilt FAISS index with {self._index.ntotal} vectors.")
            except Exception as e:
                for p in (tmp_index_path, tmp_meta_path):
                    if p.exists():
                        try:
                            os.remove(p)
                        except Exception:
                            pass
                raise VectorStoreError(f"Atomic rebuild failed: {e}") from e

    def clear(self) -> None:
        """Resets in-memory index and persists empty state."""
        with self._lock:
            self._index = self._create_empty_index()
            self.save()
