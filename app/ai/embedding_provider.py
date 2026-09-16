"""Embedding Provider Port & Google Gemini Adapter.

Phase 06: Implements Q45, Q46, Q51.
Provides a decoupled abstract port for vector generation and the Google GenAI implementation
using the verified 'gemini-embedding-001' model at 768 dimensions.
"""

from abc import ABC, abstractmethod
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)


# ==============================================================================
# PROVIDER EXCEPTIONS
# ==============================================================================

class EmbeddingProviderError(Exception):
    """Base exception for all embedding provider errors."""
    pass


class EmbeddingConfigurationError(EmbeddingProviderError):
    """Raised when provider configuration or API key is missing/invalid."""
    pass


class EmbeddingGenerationError(EmbeddingProviderError):
    """Raised when vector generation fails at the provider API level."""
    pass


# ==============================================================================
# ABSTRACT PORT
# ==============================================================================

class EmbeddingProvider(ABC):
    """Abstract boundary interface for embedding generation."""

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Generates a dense vector embedding for the given input text."""
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """Returns the vector dimensionality produced by this provider."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Returns the underlying model name/identifier."""
        pass


# ==============================================================================
# GOOGLE GEMINI ADAPTER
# ==============================================================================

class GoogleGeminiEmbeddingProvider(EmbeddingProvider):
    """Google Gemini GenAI embedding adapter.

    Uses the verified 'gemini-embedding-001' model configured with output_dimensionality=768.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-embedding-001",
        dimension: int = 768
    ):
        self.model_name = model_name
        self.dimension = dimension
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not self._api_key:
                raise EmbeddingConfigurationError(
                    "Gemini API key is required. Set GEMINI_API_KEY in environment or pass api_key."
                )
            try:
                from google import genai
                self._client = genai.Client(api_key=self._api_key)
            except Exception as e:
                raise EmbeddingConfigurationError(f"Failed to initialize google-genai client: {e}") from e
        return self._client

    def embed_text(self, text: str) -> list[float]:
        """Calls Google GenAI embed_content API and returns a 768-dimensional float list.
        
        Applies a single-owner bounded retry policy (max 2 attempts) for transient failures.
        """
        if not text or not text.strip():
            raise EmbeddingGenerationError("Cannot generate embedding for empty or whitespace text.")

        client = self._get_client()
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                from google.genai import types
                config = types.EmbedContentConfig(
                    output_dimensionality=self.dimension
                )
                response = client.models.embed_content(
                    model=self.model_name,
                    contents=text,
                    config=config
                )

                if not response.embeddings or not response.embeddings[0].values:
                    raise EmbeddingGenerationError("Gemini API returned an empty embedding vector.")

                vector = list(response.embeddings[0].values)
                if len(vector) != self.dimension:
                    raise EmbeddingGenerationError(
                        f"Expected vector of dimension {self.dimension}, but got {len(vector)}."
                    )
                return vector

            except EmbeddingProviderError:
                raise
            except Exception as e:
                if attempt < max_attempts:
                    logger.warning(
                        f"Gemini embedding transient failure on attempt {attempt}/{max_attempts}: {e}. Retrying in 0.5s..."
                    )
                    time.sleep(0.5)
                else:
                    raise EmbeddingGenerationError(f"Gemini embedding API call failed after {max_attempts} attempts: {e}") from e

    def get_dimension(self) -> int:
        return self.dimension

    def get_model_name(self) -> str:
        return self.model_name
