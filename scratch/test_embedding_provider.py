"""Test Suite: EmbeddingProvider Abstraction & Google Gemini Adapter.

Phase 06 Verification: Tests 15, 16
- Abstract boundary interface
- Mock provider implementation
- Dimensional validation
- Configuration and API failure error translation
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import MagicMock, patch
from app.ai.embedding_provider import (
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingConfigurationError,
    EmbeddingGenerationError,
    GoogleGeminiEmbeddingProvider
)


class FakeEmbeddingProvider(EmbeddingProvider):
    """Mock implementation of EmbeddingProvider port for unit testing."""

    def __init__(self, dimension: int = 768, model_name: str = "mock-embedding-v1"):
        self.dimension = dimension
        self.model_name = model_name
        self.call_count = 0

    def embed_text(self, text: str) -> list[float]:
        self.call_count += 1
        if "error" in text.lower():
            raise EmbeddingGenerationError("Simulated upstream provider outage")
        # Return deterministic unit-norm vector
        vec = [0.0] * self.dimension
        vec[0] = 1.0
        return vec

    def get_dimension(self) -> int:
        return self.dimension

    def get_model_name(self) -> str:
        return self.model_name


def test_provider_port_interface():
    print("\n--- TEST 1: EmbeddingProvider Port Interface & Mocking ---")
    provider = FakeEmbeddingProvider(dimension=768)
    assert provider.get_dimension() == 768
    assert provider.get_model_name() == "mock-embedding-v1"

    vec = provider.embed_text("Title: Nike Shoes")
    assert len(vec) == 768
    assert vec[0] == 1.0
    assert provider.call_count == 1
    print("[PASS] EmbeddingProvider port interface operates correctly.")


def test_google_gemini_provider_validation():
    print("\n--- TEST 2: GoogleGeminiEmbeddingProvider Configuration & Error Handling ---")
    # Missing API key
    with patch.dict(os.environ, {}, clear=True):
        provider = GoogleGeminiEmbeddingProvider(api_key=None)
        try:
            provider.embed_text("Sample text")
            assert False, "Expected EmbeddingConfigurationError when API key is missing"
        except EmbeddingConfigurationError as e:
            assert "Gemini API key is required" in str(e)

    # Empty text rejection
    provider_with_key = GoogleGeminiEmbeddingProvider(api_key="fake-key-for-test")
    try:
        provider_with_key.embed_text("   ")
        assert False, "Expected EmbeddingGenerationError on empty text"
    except EmbeddingGenerationError as e:
        assert "Cannot generate embedding for empty" in str(e)
    print("[PASS] Configuration and empty input validation verified.")


def test_google_gemini_provider_mocked_call():
    print("\n--- TEST 3: GoogleGeminiEmbeddingProvider Mocked Response & Dimension Check ---")
    provider = GoogleGeminiEmbeddingProvider(
        api_key="fake-key",
        model_name="gemini-embedding-001",
        dimension=768
    )

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_embedding = MagicMock()
    mock_embedding.values = [0.01] * 768
    mock_response.embeddings = [mock_embedding]
    mock_client.models.embed_content.return_value = mock_response

    with patch.object(provider, "_get_client", return_value=mock_client):
        vec = provider.embed_text("Title: Valid Product")
        assert len(vec) == 768
        assert vec[0] == 0.01

        # Check call arguments
        mock_client.models.embed_content.assert_called_once()
        kwargs = mock_client.models.embed_content.call_args.kwargs
        assert kwargs["model"] == "gemini-embedding-001"
        assert kwargs["contents"] == "Title: Valid Product"
        assert kwargs["config"].output_dimensionality == 768

    # Dimension mismatch check
    mock_bad_embedding = MagicMock()
    mock_bad_embedding.values = [0.01] * 512
    mock_response.embeddings = [mock_bad_embedding]
    with patch.object(provider, "_get_client", return_value=mock_client):
        try:
            provider.embed_text("Title: Product")
            assert False, "Expected dimension mismatch error"
        except EmbeddingGenerationError as e:
            assert "dimension 768, but got 512" in str(e)

    print("[PASS] Mocked GenAI client call, parameters, and dimension checks verified.")


def main():
    print("=" * 60)
    print("RUNNING EMBEDDING PROVIDER TEST SUITE")
    print("=" * 60)
    test_provider_port_interface()
    test_google_gemini_provider_validation()
    test_google_gemini_provider_mocked_call()
    print("=" * 60)
    print("ALL 3 PROVIDER TEST SUITES PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    main()
