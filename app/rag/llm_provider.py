"""RAG LLM Provider Port Abstraction.

Implements Q81:
- Dedicated RAGLLMProvider interface/port.
- Decouples RAG business logic from the underlying LLM provider SDK.
- Clean typed boundary consuming RAGPromptPayload and returning typed RAGModelResponse.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from app.schemas.rag import RAGModelResponse, RAGPromptPayload


class RAGProviderError(Exception):
    """Base exception for RAG LLM provider errors."""
    pass


class RAGProviderConfigurationError(RAGProviderError):
    """Raised when provider configuration or API key is missing."""
    pass


class RAGProviderResponseError(RAGProviderError):
    """Raised when LLM output violates schema or fails parsing."""
    pass


class RAGLLMProvider(ABC):
    """Abstract port for RAG structured generation."""

    @abstractmethod
    def generate(
        self,
        payload: RAGPromptPayload
    ) -> tuple[RAGModelResponse, dict[str, Any]]:
        """Generates a structured RAG model response conforming to RAGModelResponse.

        Args:
            payload: Typed prompt payload containing system instruction, structured context, and version.

        Returns:
            Tuple of (RAGModelResponse, telemetry_dict).
            telemetry_dict contains: 'model_name', 'latency_ms', 'input_tokens', 'output_tokens'.

        Raises:
            RAGProviderError on generation or schema validation failure.
        """
        pass
