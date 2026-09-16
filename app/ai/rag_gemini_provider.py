"""Google Gemini RAG Provider Adapter.

Implements Q81, Q82:
- Concrete adapter implementing RAGLLMProvider port.
- Uses modern Google GenAI SDK (google.genai) with provider-native structured output.
- Requests response_schema=RAGModelResponse and response_mime_type='application/json'.
- Validates model output through Pydantic contract.
- Captures runtime model, latency, and token metrics from usage_metadata when provided.
- Gracefully handles injected test/mock clients.
"""

import json
import logging
import os
import time
from typing import Any, Optional

from pydantic import ValidationError

from app.rag.llm_provider import (
    RAGLLMProvider,
    RAGProviderConfigurationError,
    RAGProviderError,
    RAGProviderResponseError,
)
from app.schemas.rag import RAGConfig, RAGModelResponse, RAGPromptPayload

logger = logging.getLogger(__name__)


class GoogleGeminiRAGProvider(RAGLLMProvider):
    """Google Gemini adapter for Grounded RAG structured output."""

    def __init__(
        self,
        config: Optional[RAGConfig] = None,
        client: Optional[Any] = None,
        api_key: Optional[str] = None
    ):
        self.config = config or RAGConfig()
        self._client = client
        self.api_key = (
            api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        )

    def _get_client(self) -> Any:
        """Resolves or lazily instantiates the Gemini SDK client."""
        if self._client is not None:
            return self._client

        if not self.api_key:
            raise RAGProviderConfigurationError(
                "Gemini API key is not configured. Set GEMINI_API_KEY or pass api_key."
            )

        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
            return self._client
        except ImportError:
            raise RAGProviderConfigurationError(
                "The 'google-genai' SDK is not installed in the environment."
            )

    def generate(
        self,
        payload: RAGPromptPayload
    ) -> tuple[RAGModelResponse, dict[str, Any]]:
        """Generates a structured RAGModelResponse via Gemini."""
        client = self._get_client()
        start_time = time.perf_counter()

        raw_response: Any = None
        input_tokens: Optional[int] = None
        output_tokens: Optional[int] = None

        try:
            # 1. Real Google GenAI SDK client: client.models.generate_content(...)
            if hasattr(client, "models") and hasattr(client.models, "generate_content") and not hasattr(client, "generate_content"):
                from google.genai import types

                config = types.GenerateContentConfig(
                    system_instruction=payload.system_instruction,
                    temperature=self.config.temperature,
                    max_output_tokens=self.config.max_output_tokens,
                    response_mime_type="application/json",
                    response_schema=RAGModelResponse,
                )

                raw_response = client.models.generate_content(
                    model=self.config.model_name,
                    contents=[payload.user_text],
                    config=config,
                )

                # Usage metadata from SDK response
                if hasattr(raw_response, "usage_metadata") and raw_response.usage_metadata is not None:
                    meta = raw_response.usage_metadata
                    input_tokens = getattr(meta, "prompt_token_count", None)
                    output_tokens = getattr(meta, "candidates_token_count", None)

            # 2. Injected mock client with generate_content method
            elif hasattr(client, "generate_content"):
                raw_response = client.generate_content(
                    model=self.config.model_name,
                    system_instruction=payload.system_instruction,
                    user_text=payload.user_text,
                    response_schema=RAGModelResponse,
                )
                if isinstance(raw_response, tuple) and len(raw_response) == 2:
                    raw_response, mock_meta = raw_response
                    input_tokens = mock_meta.get("input_tokens")
                    output_tokens = mock_meta.get("output_tokens")

            # 3. Direct callable mock
            elif callable(client):
                raw_response = client(payload)

            else:
                raise RAGProviderConfigurationError(
                    f"Unsupported client object {type(client)} for GoogleGeminiRAGProvider."
                )

        except (RAGProviderConfigurationError, RAGProviderResponseError):
            raise
        except Exception as e:
            raise RAGProviderError(f"Gemini API call failed during RAG generation: {e}") from e

        took_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        parsed_response = self._parse_model_response(raw_response)

        telemetry = {
            "model_name": self.config.model_name,
            "latency_ms": took_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        return parsed_response, telemetry

    def _parse_model_response(self, raw_response: Any) -> RAGModelResponse:
        """Parses and validates the raw response against the RAGModelResponse contract."""
        if isinstance(raw_response, RAGModelResponse):
            return raw_response

        # Response object with parsed attribute
        if hasattr(raw_response, "parsed") and raw_response.parsed is not None:
            if isinstance(raw_response.parsed, RAGModelResponse):
                return raw_response.parsed
            if isinstance(raw_response.parsed, dict):
                try:
                    return RAGModelResponse.model_validate(raw_response.parsed)
                except ValidationError as ve:
                    raise RAGProviderResponseError(f"Schema validation failed on parsed output: {ve}") from ve

        # Response object with text attribute
        text: Optional[str] = None
        if hasattr(raw_response, "text") and isinstance(raw_response.text, str):
            text = raw_response.text
        elif isinstance(raw_response, str):
            text = raw_response
        elif isinstance(raw_response, dict):
            try:
                return RAGModelResponse.model_validate(raw_response)
            except ValidationError as ve:
                raise RAGProviderResponseError(f"Schema validation failed on dict output: {ve}") from ve

        if text is not None:
            cleaned = text.strip()
            # Strip code block fences if present
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError as je:
                raise RAGProviderResponseError(f"Failed to decode response as JSON: {je}") from je

            try:
                return RAGModelResponse.model_validate(data)
            except ValidationError as ve:
                raise RAGProviderResponseError(f"RAG response violated RAGModelResponse schema: {ve}") from ve

        raise RAGProviderResponseError(f"Unrecognized response format from LLM provider: {type(raw_response)}")
