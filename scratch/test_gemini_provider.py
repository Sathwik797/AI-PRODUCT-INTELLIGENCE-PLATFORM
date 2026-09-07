import sys
sys.path.insert(0, ".")

import json
import os
from unittest.mock import MagicMock
import app.ai.gemini_provider as gp
from app.ai.gemini_provider import (
    AIImageInput,
    AIProductContext,
    GeminiAPIError,
    GeminiConfig,
    GeminiConfigurationError,
    GeminiProvider,
    GeminiProviderError,
    GeminiResponseValidationError,
)
from app.schemas.ai_metadata import AIProductMetadata

print("=" * 60)
print("RUNNING GEMINI PROVIDER FOUNDATION TEST SUITE")
print("=" * 60)

passed = 0
failed = 0

def run_test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"[PASS] {name}")
        passed += 1
    except Exception as e:
        print(f"[FAIL] {name} -> {e}")
        import traceback
        traceback.print_exc()
        failed += 1

# Sample valid payload matching AIProductMetadata contract
VALID_AI_PAYLOAD = {
    "title": {
        "type": "text",
        "value": "Nike Pegasus 40 Men's Road Running Shoes",
        "confidence": 0.96,
        "evidence": {
            "source": {"type": "image", "image_id": 1},
            "explanation": "Visible on lateral side"
        }
    },
    "description": {
        "type": "text",
        "value": "Responsive road running shoes for daily training.",
        "confidence": 0.90,
        "evidence": {
            "source": {"type": "seller"},
            "explanation": "From seller catalog"
        }
    },
    "brand": {
        "type": "text",
        "value": "Nike",
        "confidence": 0.99,
        "evidence": {
            "source": {"type": "image", "image_id": 1},
            "explanation": "Swoosh logo visible"
        }
    },
    "category": {
        "value": {
            "recommended_category_id": 1,
            "recommended_category_name": "Footwear",
            "proposed_category": "Running Shoes"
        },
        "confidence": 0.95,
        "evidence": {
            "source": {"type": "image", "image_id": 1},
            "explanation": "Running shoe sole pattern"
        }
    },
    "tags": ["running", "footwear"],
    "keywords": ["nike pegasus", "mens runner"],
    "attributes": {
        "color": {
            "type": "text",
            "value": "Black / White",
            "confidence": 0.95,
            "evidence": {
                "source": {"type": "image", "image_id": 2},
                "explanation": "Upper color pattern"
            }
        }
    }
}

# Test 1: Provider configuration missing API key is handled correctly
def test_1_missing_api_key():
    old_gemini = os.environ.pop("GEMINI_API_KEY", None)
    old_google = os.environ.pop("GOOGLE_API_KEY", None)

    from unittest.mock import patch
    with patch("dotenv.load_dotenv"):
        try:
            config = GeminiConfig(api_key=None)
            provider = GeminiProvider(config=config)
            context = AIProductContext(product_id=1, title="Test")

            try:
                provider.generate_product_metadata(context)
                raise AssertionError("Should have raised GeminiConfigurationError")
            except GeminiConfigurationError as e:
                assert "API key is not configured" in str(e)
        finally:
            if old_gemini:
                os.environ["GEMINI_API_KEY"] = old_gemini
            if old_google:
                os.environ["GOOGLE_API_KEY"] = old_google

run_test("1. Provider configuration missing API key is handled correctly", test_1_missing_api_key)

# Test 2: Provider constructs a multimodal request with multiple images & updated grounding prompt
def test_2_multimodal_request_construction():
    img1 = AIImageInput(image_id=101, image_bytes=b"fake_jpeg_1", mime_type="image/jpeg", display_order=1)
    img2 = AIImageInput(image_id=102, image_bytes=b"fake_png_2", mime_type="image/png", display_order=2)

    context = AIProductContext(
        product_id=42,
        title="Sample Product",
        description="Sample Description",
        brand="BrandX",
        price=49.99,
        category_hint="Apparel",
        existing_categories=["Footwear", "Apparel", "Accessories"],
        images=[img1, img2]
    )

    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    request = provider.build_multimodal_request(context)

    # Verify context & images
    assert "Product ID: 42" in request["user_text"]
    assert "Sample Product" in request["user_text"]
    assert "image_id=101" in request["user_text"]
    assert "image_id=102" in request["user_text"]
    assert len(request["images"]) == 2
    assert request["images"][0]["image_id"] == 101
    assert request["images"][0]["bytes"] == b"fake_jpeg_1"
    assert request["images"][1]["image_id"] == 102
    assert request["images"][1]["bytes"] == b"fake_png_2"

    # Verify updated grounding instructions in system prompt
    prompt = request["system_instruction"]
    assert "image: Information directly supported by the supplied image" in prompt.replace("'", "")
    assert "seller: Information explicitly supplied by seller/product context" in prompt.replace("'", "")
    assert "inferred: A genuine inference derived from available evidence" in prompt.replace("'", "")
    assert "Never represent inferred information as directly observed visual fact." in prompt

run_test("2. Provider constructs a multimodal request with multiple images", test_2_multimodal_request_construction)

# Test 3: Structured response is passed through AIProductMetadata validation
def test_3_structured_response_validation():
    # 3a. Direct generate_content mock
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(VALID_AI_PAYLOAD)
    mock_client.generate_content.return_value = mock_response

    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"), client=mock_client)
    context = AIProductContext(product_id=1)

    result = provider.generate_product_metadata(context)
    assert isinstance(result, AIProductMetadata)
    assert result.title.value == "Nike Pegasus 40 Men's Road Running Shoes"
    assert result.brand.value == "Nike"
    assert result.category.value.recommended_category_name == "Footwear"

    # 3b. Modern Google GenAI SDK client interface mock (client.models.generate_content)
    modern_mock_client = MagicMock(spec=["models"])
    modern_mock_response = MagicMock()
    modern_mock_response.text = json.dumps(VALID_AI_PAYLOAD)
    modern_mock_client.models.generate_content.return_value = modern_mock_response

    provider_modern = GeminiProvider(config=GeminiConfig(api_key="test-key"), client=modern_mock_client)
    result_modern = provider_modern.generate_product_metadata(context)
    assert isinstance(result_modern, AIProductMetadata)
    assert result_modern.title.value == "Nike Pegasus 40 Men's Road Running Shoes"

run_test("3. Structured response is passed through AIProductMetadata validation", test_3_structured_response_validation)

# Test 4: Invalid structured response raises provider-level validation error
def test_4_invalid_structured_response():
    mock_client = MagicMock()
    mock_response = MagicMock()
    # Confidence > 1 is invalid according to our schema
    invalid_payload = {**VALID_AI_PAYLOAD, "title": {**VALID_AI_PAYLOAD["title"], "confidence": 1.5}}
    mock_response.text = json.dumps(invalid_payload)
    mock_client.generate_content.return_value = mock_response

    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"), client=mock_client)
    context = AIProductContext(product_id=1)

    try:
        provider.generate_product_metadata(context)
        raise AssertionError("Should have raised GeminiResponseValidationError")
    except GeminiResponseValidationError as e:
        assert isinstance(e, GeminiProviderError)
        assert "failed validation against AIProductMetadata" in str(e)

run_test("4. Invalid structured response raises provider-level validation error", test_4_invalid_structured_response)

# Test 5: Gemini/provider exception is translated to provider-level exception
def test_5_exception_translation():
    mock_client = MagicMock()
    mock_client.generate_content.side_effect = RuntimeError("Connection aborted by remote peer")

    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"), client=mock_client)
    context = AIProductContext(product_id=1)

    try:
        provider.generate_product_metadata(context)
        raise AssertionError("Should have raised GeminiAPIError")
    except GeminiAPIError as e:
        assert isinstance(e, GeminiProviderError)
        assert "Connection aborted" in str(e)

run_test("5. Gemini/provider exception is translated to provider-level exception", test_5_exception_translation)

# Test 6: No FastAPI HTTPException is used inside the provider
def test_6_no_http_exception():
    # Verify HTTPException is not imported or present in provider module attributes
    assert "HTTPException" not in gp.__dict__, "HTTPException found in provider module dict!"
    assert "fastapi" not in gp.__dict__, "fastapi module found in provider module dict!"

    # Also verify that when errors occur, provider raises GeminiProviderError, never HTTPException
    mock_client = MagicMock()
    mock_client.generate_content.side_effect = ValueError("Simulated error")
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"), client=mock_client)
    try:
        provider.generate_product_metadata(AIProductContext(product_id=1))
    except Exception as e:
        assert isinstance(e, GeminiProviderError)
        assert type(e).__name__ != "HTTPException"

run_test("6. No FastAPI HTTPException is used inside the provider", test_6_no_http_exception)

# Test 7: No SQLAlchemy Product object is required by the provider & no legacy SDK
def test_7_no_sqlalchemy_dependency():
    # Verify no SQLAlchemy imports exist in the provider module
    assert "sqlalchemy" not in gp.__dict__, "SQLAlchemy dependency found in provider module!"
    assert "Product" not in gp.__dict__, "Product model import found in provider module!"

    # Verify no legacy google.generativeai import or fallback exists
    with open("app/ai/gemini_provider.py", "r", encoding="utf-8") as f:
        src = f.read()
    assert "google.generativeai" not in src, "Legacy google.generativeai found in source code!"

    # Verify provider works with purely python primitive context and dataclass
    mock_client = MagicMock()
    mock_client.generate_content.return_value = VALID_AI_PAYLOAD
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"), client=mock_client)

    pure_context = AIProductContext(
        product_id=999,
        title="Pure Python Title",
        images=[AIImageInput(image_id=1, image_bytes=b"raw_bytes")]
    )
    res = provider.generate_product_metadata(pure_context)
    assert res.title.value == "Nike Pegasus 40 Men's Road Running Shoes"

run_test("7. No SQLAlchemy Product object is required by the provider", test_7_no_sqlalchemy_dependency)

print("=" * 60)
print(f"FINAL RESULTS: {passed} PASSED, {failed} FAILED")
print("=" * 60)
if failed > 0:
    sys.exit(1)
