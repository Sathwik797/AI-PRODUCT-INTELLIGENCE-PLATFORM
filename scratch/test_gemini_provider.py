import sys
sys.path.insert(0, ".")

import json
import os
from unittest.mock import MagicMock
import app.ai.gemini_provider as gp
from app.ai.gemini_provider import (
    AIImageInput,
    AIProductContext,
    AttributeItemWire,
    CategoryFieldWire,
    CategoryValueWire,
    EvidenceSourceWire,
    EvidenceWire,
    GeminiAPIError,
    GeminiConfig,
    GeminiConfigurationError,
    GeminiProductMetadataWire,
    GeminiProvider,
    GeminiProviderError,
    GeminiResponseValidationError,
    TextFieldWire,
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

# Sample valid payload matching GeminiProductMetadataWire contract
VALID_WIRE_PAYLOAD = {
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
    "attributes": [
        {
            "name": "color",
            "type": "text",
            "value": "Black / White",
            "confidence": 0.95,
            "evidence": {
                "source": {"type": "image", "image_id": 2},
                "explanation": "Upper color pattern"
            }
        },
        {
            "name": "weight",
            "type": "measurement",
            "value": 280,
            "unit": "g",
            "confidence": 0.92,
            "evidence": {
                "source": {"type": "seller"},
                "explanation": "Spec sheet weight"
            }
        },
        {
            "name": "eco_friendly",
            "type": "boolean",
            "value": True,
            "confidence": 0.85,
            "evidence": {
                "source": {"type": "inferred"},
                "explanation": "Recycled materials claim"
            }
        }
    ]
}

# Test A: GeminiProductMetadataWire converts successfully through Google GenAI schema transformer
def test_a_schema_transformer():
    from google.genai._transformers import t_schema
    s = t_schema(None, GeminiProductMetadataWire)
    assert s is not None
    assert str(s.type).upper() == "TYPE.OBJECT"

run_test("A. GeminiProductMetadataWire converts successfully through schema transformer", test_a_schema_transformer)

# Test B: A valid wire response converts to AIProductMetadata
def test_b_valid_wire_converts():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    res = provider._parse_and_validate_response(VALID_WIRE_PAYLOAD)
    assert isinstance(res, AIProductMetadata)
    assert res.title.value == "Nike Pegasus 40 Men's Road Running Shoes"

run_test("B. A valid wire response converts to AIProductMetadata", test_b_valid_wire_converts)

# Test C: Attribute list converts correctly into domain attribute dictionary
def test_c_attribute_list_to_dict():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    res = provider._parse_and_validate_response(VALID_WIRE_PAYLOAD)
    assert isinstance(res.attributes, dict)
    assert "color" in res.attributes
    assert "weight" in res.attributes
    assert "eco_friendly" in res.attributes

run_test("C. Attribute list converts correctly into domain attribute dictionary", test_c_attribute_list_to_dict)

# Test D: Multiple attributes preserve their names
def test_d_multiple_attribute_names():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    res = provider._parse_and_validate_response(VALID_WIRE_PAYLOAD)
    assert set(res.attributes.keys()) == {"color", "weight", "eco_friendly"}

run_test("D. Multiple attributes preserve their names", test_d_multiple_attribute_names)

# Test E: Confidence is preserved exactly
def test_e_confidence_preserved():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    res = provider._parse_and_validate_response(VALID_WIRE_PAYLOAD)
    assert res.title.confidence == 0.96
    assert res.brand.confidence == 0.99
    assert res.attributes["color"].confidence == 0.95
    assert res.attributes["weight"].confidence == 0.92

run_test("E. Confidence is preserved exactly", test_e_confidence_preserved)

# Test F: Evidence is preserved exactly
def test_f_evidence_preserved():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    res = provider._parse_and_validate_response(VALID_WIRE_PAYLOAD)
    assert res.title.evidence.explanation == "Visible on lateral side"
    assert res.attributes["weight"].evidence.explanation == "Spec sheet weight"

run_test("F. Evidence is preserved exactly", test_f_evidence_preserved)

# Test G: Image evidence preserves image_id
def test_g_image_evidence_id():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    res = provider._parse_and_validate_response(VALID_WIRE_PAYLOAD)
    assert res.title.evidence.source.type == "image"
    assert res.title.evidence.source.image_id == 1
    assert res.attributes["color"].evidence.source.type == "image"
    assert res.attributes["color"].evidence.source.image_id == 2

run_test("G. Image evidence preserves image_id", test_g_image_evidence_id)

# Test H: Seller evidence remains seller evidence
def test_h_seller_evidence():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    res = provider._parse_and_validate_response(VALID_WIRE_PAYLOAD)
    assert res.description.evidence.source.type == "seller"
    assert res.attributes["weight"].evidence.source.type == "seller"

run_test("H. Seller evidence remains seller evidence", test_h_seller_evidence)

# Test I: Inferred evidence remains inferred evidence
def test_i_inferred_evidence():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    res = provider._parse_and_validate_response(VALID_WIRE_PAYLOAD)
    assert res.attributes["eco_friendly"].evidence.source.type == "inferred"

run_test("I. Inferred evidence remains inferred evidence", test_i_inferred_evidence)

# Test J: Unsupported attribute type fails strict domain validation
def test_j_unsupported_attribute_type_fails():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    bad_payload = dict(VALID_WIRE_PAYLOAD)
    bad_payload["attributes"] = [
        {
            "name": "weird_attr",
            "type": "unsupported_magic_type",
            "value": "something",
            "confidence": 0.8,
            "evidence": {"source": {"type": "inferred"}, "explanation": "test"}
        }
    ]
    try:
        provider._parse_and_validate_response(bad_payload)
        raise AssertionError("Should have failed validation for unsupported attribute type")
    except GeminiResponseValidationError as e:
        assert "validation error" in str(e).lower()

run_test("J. Unsupported attribute type fails strict domain validation", test_j_unsupported_attribute_type_fails)

# Test K: Missing confidence fails wire validation
def test_k_missing_confidence_fails():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    bad_payload = json.loads(json.dumps(VALID_WIRE_PAYLOAD))
    del bad_payload["title"]["confidence"]
    try:
        provider._parse_and_validate_response(bad_payload)
        raise AssertionError("Should have failed validation for missing confidence")
    except GeminiResponseValidationError as e:
        assert "validation error" in str(e).lower()

run_test("K. Missing confidence fails wire validation", test_k_missing_confidence_fails)

# Test L: Missing evidence fails wire validation
def test_l_missing_evidence_fails():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    bad_payload = json.loads(json.dumps(VALID_WIRE_PAYLOAD))
    del bad_payload["brand"]["evidence"]
    try:
        provider._parse_and_validate_response(bad_payload)
        raise AssertionError("Should have failed validation for missing evidence")
    except GeminiResponseValidationError as e:
        assert "validation error" in str(e).lower()

run_test("L. Missing evidence fails wire validation", test_l_missing_evidence_fails)

# Test M: Flat title string does NOT get silently coerced
def test_m_flat_title_not_coerced():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    bad_payload = json.loads(json.dumps(VALID_WIRE_PAYLOAD))
    bad_payload["title"] = "Flat Nike Title String"
    try:
        provider._parse_and_validate_response(bad_payload)
        raise AssertionError("Should have failed validation for flat title string")
    except GeminiResponseValidationError as e:
        assert "validation error" in str(e).lower()

run_test("M. Flat title string does NOT get silently coerced", test_m_flat_title_not_coerced)

# Test N: Flat brand string does NOT get silently coerced
def test_n_flat_brand_not_coerced():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    bad_payload = json.loads(json.dumps(VALID_WIRE_PAYLOAD))
    bad_payload["brand"] = "Nike"
    try:
        provider._parse_and_validate_response(bad_payload)
        raise AssertionError("Should have failed validation for flat brand string")
    except GeminiResponseValidationError as e:
        assert "validation error" in str(e).lower()

run_test("N. Flat brand string does NOT get silently coerced", test_n_flat_brand_not_coerced)

# Test O: Existing wrapper normalization still works if a wrapper is present
def test_o_wrapper_normalization_works():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    wrapped = {"product_metadata": VALID_WIRE_PAYLOAD}
    res = provider._parse_and_validate_response(wrapped)
    assert res.title.value == "Nike Pegasus 40 Men's Road Running Shoes"
    assert "color" in res.attributes

run_test("O. Existing wrapper normalization still works if a wrapper is present", test_o_wrapper_normalization_works)

# Test P: Unknown wrapper still fails
def test_p_unknown_wrapper_fails():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    wrapped = {"unauthorized_envelope": VALID_WIRE_PAYLOAD}
    try:
        provider._parse_and_validate_response(wrapped)
        raise AssertionError("Should have failed for unknown wrapper")
    except GeminiResponseValidationError as e:
        assert "validation error" in str(e).lower()

run_test("P. Unknown wrapper still fails", test_p_unknown_wrapper_fails)

# Test Q: Existing provider behavior remains intact (domain payload still parses directly)
def test_q_existing_domain_payload_parses():
    provider = GeminiProvider(config=GeminiConfig(api_key="test-key"))
    res = provider._parse_and_validate_response(VALID_AI_PAYLOAD)
    assert res.title.value == "Nike Pegasus 40 Men's Road Running Shoes"
    assert "color" in res.attributes

run_test("Q. Existing provider behavior remains intact (domain payload parses directly)", test_q_existing_domain_payload_parses)

print("=" * 60)
print(f"FINAL RESULTS: {passed} PASSED, {failed} FAILED")
print("=" * 60)
if failed > 0:
    sys.exit(1)
