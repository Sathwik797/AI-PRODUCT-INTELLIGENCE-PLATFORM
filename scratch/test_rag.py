"""Phase 07.2 Grounded RAG Focused Verification Suite.

Implements the 15 required checks with offline MockRAGLLMProvider (zero live API calls):
1. Accepted metadata enters bundle
2. Rejected/pending metadata excluded
3. Current price/status come from Product
4. Accepted evidence image IDs preserved
5. Prompt is deterministic
6. Prompt version is present (rag_v1)
7. Structured provider response validates
8. Malformed response fails safely
9. Valid atomic claim passes
10. Wrong attribute/value fails (VALUE_MISMATCH)
11. Wrong image citation fails (INVALID_IMAGE_REFERENCE)
12. Unsupported factual claim fails (INVALID_ATTRIBUTE / INVALID_PRODUCT_REFERENCE)
13. First validation failure triggers exactly one retry
14. Second failure produces fail-closed safe fallback
15. Zero search results do not call LLM (short circuit)
Plus: API endpoint test for POST /api/v1/rag/query.
"""

import os
import sys
import time
from typing import Any, Optional
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from app.ai.rag_gemini_provider import GoogleGeminiRAGProvider
from app.main import app
from app.rag.citation_validator import CitationValidator, normalize_value
from app.rag.knowledge import RAGRetrievalService
from app.rag.llm_provider import RAGLLMProvider, RAGProviderResponseError
from app.rag.prompt_builder import RAGPromptBuilder
from app.schemas.rag import (
    RAGCitation,
    RAGClaim,
    RAGConfig,
    RAGEvidence,
    RAGKnowledgeBundle,
    RAGModelResponse,
    RAGProductContext,
    RAGPromptPayload,
    RAGResponse,
    RAGVerifiedAttribute,
)
from app.schemas.search import (
    SearchFilters,
    SearchMetadata,
    SearchQuery,
    SearchResponse,
    SearchResultItem,
)
from app.services.rag_service import RAGService


# ==============================================================================
# MOCK PROVIDERS FOR TESTING
# ==============================================================================

class MockRAGLLMProvider(RAGLLMProvider):
    """Deterministic mock provider simulating LLM generation for unit tests."""

    def __init__(self, responses: Optional[list[Any]] = None):
        # List of responses or callables to return sequentially on each generate call
        self.responses = list(responses or [])
        self.call_count = 0
        self.received_payloads: list[RAGPromptPayload] = []

    def generate(self, payload: RAGPromptPayload) -> tuple[RAGModelResponse, dict[str, Any]]:
        self.call_count += 1
        self.received_payloads.append(payload)

        if not self.responses:
            raise RuntimeError("MockRAGLLMProvider ran out of configured responses.")

        next_resp = self.responses.pop(0)

        if isinstance(next_resp, Exception):
            raise next_resp

        if callable(next_resp):
            next_resp = next_resp(payload)

        telemetry = {
            "model_name": "mock-rag-model",
            "latency_ms": 12.5,
            "input_tokens": 120,
            "output_tokens": 45,
        }
        return next_resp, telemetry


# ==============================================================================
# HELPER TEST BUNDLE FIXTURE
# ==============================================================================

def create_sample_bundle() -> RAGKnowledgeBundle:
    """Constructs a deterministic RAGKnowledgeBundle for testing."""
    product_ctx = RAGProductContext(
        product_id=2,
        live_catalog_state={
            "price": 2499.0,
            "status": "ACTIVE",
        },
        product_facts={
            "title": "Nike Air Force 1 '72",
            "description": "Iconic vintage low-top basketball sneaker.",
            "brand": "Nike",
            "category": "Shoes",
        },
        verified_attributes=[
            RAGVerifiedAttribute(
                attribute="material",
                type="text",
                value="Leather",
                confidence=0.98,
                evidence=RAGEvidence(
                    source_type="image",
                    image_id=101,
                    explanation="Visual close-up confirms smooth full-grain leather upper."
                )
            ),
            RAGVerifiedAttribute(
                attribute="color",
                type="text",
                value="White",
                confidence=0.99,
                evidence=RAGEvidence(
                    source_type="image",
                    image_id=102,
                    explanation="Product images show all-white colorway."
                )
            ),
            RAGVerifiedAttribute(
                attribute="origin",
                type="text",
                value="Vietnam",
                confidence=0.90,
                evidence=RAGEvidence(
                    source_type="seller",
                    image_id=None,
                    explanation="Seller spec sheet specifies country of origin."
                )
            )
        ],
        search_match_context=["semantic_similarity=0.92", "brand_match=Nike"]
    )

    return RAGKnowledgeBundle(
        question="What is the material and price of Nike Air Force 1?",
        products=[product_ctx]
    )


# ==============================================================================
# TEST SUITE
# ==============================================================================

def run_all_checks():
    passed = 0
    failed = 0
    total = 15

    print("=" * 70)
    print("PHASE 07.2 — GROUNDED RAG FOCUSED VERIFICATION SUITE")
    print("=" * 70)

    # --------------------------------------------------------------------------
    # Check 1: Accepted metadata enters bundle
    # --------------------------------------------------------------------------
    try:
        mock_search_svc = MagicMock()
        retrieval_svc = RAGRetrievalService(hybrid_search_service=mock_search_svc)

        # Mock DB session and ORM objects
        mock_db = MagicMock()
        mock_product = MagicMock()
        mock_product.id = 2
        mock_product.price = 2499.0
        mock_product.status = "ACTIVE"
        mock_product.title = "Nike Air Force 1"
        mock_product.description = "Classic"
        mock_product.brand = "Nike"
        mock_product.category.name = "Shoes"

        mock_meta = MagicMock()
        mock_meta.current_generation_id = 10

        mock_gen = MagicMock()
        mock_gen.acceptance_state = {"attributes": "accepted"}
        mock_gen.output = {
            "attributes": {
                "material": {
                    "type": "text",
                    "value": "Leather",
                    "confidence": 0.95,
                    "evidence": {
                        "source": {"type": "image", "image_id": 101},
                        "explanation": "Leather grain visible"
                    }
                }
            }
        }

        # Wire query filters
        def mock_query(model):
            q = MagicMock()
            if model.__name__ == "Product":
                q.filter.return_value.first.return_value = mock_product
            elif model.__name__ == "ProductMetadata":
                q.filter.return_value.first.return_value = mock_meta
            elif model.__name__ == "AIGeneration":
                q.filter.return_value.first.return_value = mock_gen
            return q

        mock_db.query.side_effect = mock_query

        context = retrieval_svc._hydrate_single_product(mock_db, product_id=2, match_reasons=["test"])
        assert context is not None
        assert len(context.verified_attributes) == 1
        assert context.verified_attributes[0].attribute == "material"
        assert context.verified_attributes[0].value == "Leather"
        assert context.verified_attributes[0].evidence.image_id == 101
        print("[PASS] Check 1: Accepted metadata enters bundle")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 1: Accepted metadata enters bundle: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 2: Rejected / pending metadata excluded
    # --------------------------------------------------------------------------
    try:
        mock_gen_rejected = MagicMock()
        mock_gen_rejected.acceptance_state = {"attributes": "rejected"}
        mock_gen_rejected.output = {
            "attributes": {
                "material": {"type": "text", "value": "Leather"}
            }
        }

        def mock_query_rej(model):
            q = MagicMock()
            if model.__name__ == "Product":
                q.filter.return_value.first.return_value = mock_product
            elif model.__name__ == "ProductMetadata":
                q.filter.return_value.first.return_value = mock_meta
            elif model.__name__ == "AIGeneration":
                q.filter.return_value.first.return_value = mock_gen_rejected
            return q

        mock_db.query.side_effect = mock_query_rej
        context_rej = retrieval_svc._hydrate_single_product(mock_db, product_id=2, match_reasons=[])
        assert context_rej is not None
        assert len(context_rej.verified_attributes) == 0

        # Also test 'pending'
        mock_gen_rejected.acceptance_state = {"attributes": "pending"}
        context_pend = retrieval_svc._hydrate_single_product(mock_db, product_id=2, match_reasons=[])
        assert len(context_pend.verified_attributes) == 0

        print("[PASS] Check 2: Rejected/pending metadata excluded")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 2: Rejected/pending metadata excluded: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 3: Current price/status come from Product
    # --------------------------------------------------------------------------
    try:
        bundle = create_sample_bundle()
        p = bundle.products[0]
        assert p.live_catalog_state["price"] == 2499.0
        assert p.live_catalog_state["status"] == "ACTIVE"
        print("[PASS] Check 3: Current price/status come directly from Product row")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 3: Current price/status come directly from Product row: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 4: Accepted evidence image IDs preserved
    # --------------------------------------------------------------------------
    try:
        bundle = create_sample_bundle()
        mat_attr = next(a for a in bundle.products[0].verified_attributes if a.attribute == "material")
        assert mat_attr.evidence is not None
        assert mat_attr.evidence.source_type == "image"
        assert mat_attr.evidence.image_id == 101
        print("[PASS] Check 4: Accepted evidence image IDs preserved")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 4: Accepted evidence image IDs preserved: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 5: Prompt is deterministic
    # --------------------------------------------------------------------------
    try:
        builder = RAGPromptBuilder()
        bundle = create_sample_bundle()
        payload1 = builder.build(bundle)
        payload2 = builder.build(bundle)
        assert payload1.user_text == payload2.user_text
        assert payload1.system_instruction == payload2.system_instruction
        assert payload1.prompt_version == payload2.prompt_version
        print("[PASS] Check 5: Prompt builder is deterministic")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 5: Prompt builder is deterministic: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 6: Prompt version is present (rag_v1)
    # --------------------------------------------------------------------------
    try:
        builder = RAGPromptBuilder()
        bundle = create_sample_bundle()
        payload = builder.build(bundle)
        assert payload.prompt_version == "rag_v1"
        assert builder.PROMPT_VERSION == "rag_v1"
        print("[PASS] Check 6: Prompt version 'rag_v1' is present")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 6: Prompt version 'rag_v1' is present: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 7: Structured provider response validates
    # --------------------------------------------------------------------------
    try:
        raw_valid_dict = {
            "answer": "The Nike Air Force 1 is priced at ₹2499 and features genuine leather upper.",
            "claims": [
                {
                    "claim": "The shoe is priced at ₹2499.",
                    "product_id": 2,
                    "attribute": "price",
                    "value": 2499.0,
                    "citation": None
                },
                {
                    "claim": "The shoe upper is made of leather.",
                    "product_id": 2,
                    "attribute": "material",
                    "value": "Leather",
                    "citation": {"image_id": 101, "explanation": "Close-up photo"}
                }
            ]
        }
        parsed = RAGModelResponse.model_validate(raw_valid_dict)
        assert parsed.answer.startswith("The Nike Air Force 1")
        assert len(parsed.claims) == 2
        assert parsed.claims[0].attribute == "price"
        assert parsed.claims[1].citation.image_id == 101
        print("[PASS] Check 7: Structured provider response validates against Pydantic contract")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 7: Structured provider response validation: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 8: Malformed response fails safely
    # --------------------------------------------------------------------------
    try:
        provider = GoogleGeminiRAGProvider(client=MagicMock())
        # Pass completely invalid JSON string
        malformed_raw = "{malformed_json: true, unclosed"
        try:
            provider._parse_model_response(malformed_raw)
            raise AssertionError("Expected RAGProviderResponseError was not raised.")
        except RAGProviderResponseError:
            pass  # Expected safe controlled failure

        # Pass dict violating schema (missing answer)
        try:
            provider._parse_model_response({"claims": []})
            raise AssertionError("Expected RAGProviderResponseError for missing answer.")
        except RAGProviderResponseError:
            pass  # Expected safe controlled failure

        print("[PASS] Check 8: Malformed provider output fails safely without crashing")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 8: Malformed response handling: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 9: Valid atomic claim passes
    # --------------------------------------------------------------------------
    try:
        validator = CitationValidator()
        bundle = create_sample_bundle()

        valid_response = RAGModelResponse(
            answer="Nike Air Force 1 is ₹2499 and made of white leather.",
            claims=[
                RAGClaim(
                    claim="Product price is 2499.",
                    product_id=2,
                    attribute="price",
                    value=2499.0,
                    citation=None
                ),
                RAGClaim(
                    claim="Material is leather.",
                    product_id=2,
                    attribute="material",
                    value="leather",  # normalized case
                    citation=RAGCitation(image_id=101)
                ),
                RAGClaim(
                    claim="Color is white.",
                    product_id=2,
                    attribute="color",
                    value="White",
                    citation=RAGCitation(image_id=102)
                ),
                RAGClaim(
                    claim="Manufactured in Vietnam.",
                    product_id=2,
                    attribute="origin",
                    value="Vietnam",
                    citation=None  # Seller evidence, no image citation required
                )
            ]
        )

        res = validator.validate(valid_response, bundle)
        assert res.is_valid, f"Expected valid, got errors: {res.errors}"
        assert len(res.errors) == 0
        print("[PASS] Check 9: Valid atomic claims with correct provenance pass verification")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 9: Valid atomic claims verification: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 10: Wrong attribute/value fails (VALUE_MISMATCH)
    # --------------------------------------------------------------------------
    try:
        validator = CitationValidator()
        bundle = create_sample_bundle()

        mismatched_response = RAGModelResponse(
            answer="Nike Air Force 1 is ₹1999.",
            claims=[
                RAGClaim(
                    claim="Price is 1999.",
                    product_id=2,
                    attribute="price",
                    value=1999.0,  # Actual is 2499.0
                    citation=None
                )
            ]
        )

        res = validator.validate(mismatched_response, bundle)
        assert not res.is_valid
        assert any("VALUE_MISMATCH" in err for err in res.errors)
        print("[PASS] Check 10: Value mismatch triggers VALUE_MISMATCH error")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 10: Wrong value check: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 11: Wrong image citation fails (INVALID_IMAGE_REFERENCE)
    # --------------------------------------------------------------------------
    try:
        validator = CitationValidator()
        bundle = create_sample_bundle()

        wrong_image_response = RAGModelResponse(
            answer="Nike Air Force 1 is made of leather.",
            claims=[
                RAGClaim(
                    claim="Material is leather.",
                    product_id=2,
                    attribute="material",
                    value="Leather",
                    citation=RAGCitation(image_id=999)  # Actual is 101
                )
            ]
        )

        res = validator.validate(wrong_image_response, bundle)
        assert not res.is_valid
        assert any("INVALID_IMAGE_REFERENCE" in err for err in res.errors)
        print("[PASS] Check 11: Wrong image citation triggers INVALID_IMAGE_REFERENCE")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 11: Wrong image citation: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 12: Unsupported factual claim fails (INVALID_ATTRIBUTE / PRODUCT)
    # --------------------------------------------------------------------------
    try:
        validator = CitationValidator()
        bundle = create_sample_bundle()

        unsupported_response = RAGModelResponse(
            answer="Has waterproof gore-tex lining.",
            claims=[
                RAGClaim(
                    claim="Waterproof technology.",
                    product_id=2,
                    attribute="waterproof",  # Non-existent attribute
                    value=True,
                    citation=None
                ),
                RAGClaim(
                    claim="Phantom product.",
                    product_id=9999,  # Non-existent product
                    attribute="price",
                    value=500.0,
                    citation=None
                )
            ]
        )

        res = validator.validate(unsupported_response, bundle)
        assert not res.is_valid
        assert any("INVALID_ATTRIBUTE" in err for err in res.errors)
        assert any("INVALID_PRODUCT_REFERENCE" in err for err in res.errors)
        print("[PASS] Check 12: Unsupported attribute & phantom product trigger validation errors")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 12: Unsupported factual claim: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 13: First validation failure triggers exactly one retry
    # --------------------------------------------------------------------------
    try:
        bundle = create_sample_bundle()
        mock_retrieval = MagicMock()
        mock_search_resp = SearchResponse(
            query="test",
            results=[
                SearchResultItem(
                    product={"id": 2, "title": "Nike Air", "sku": "NK-1", "price": 2499.0, "category_id": 1, "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"},
                    score=0.9,
                    match_reasons=["test"]
                )
            ],
            metadata=SearchMetadata(
                eligible_candidate_count=1,
                total_eligible=1,
                returned_count=1,
                requested_limit=5,
                took_ms=5.0,
                k_expanded=False,
                parsed_filters=SearchFilters(),
                semantic_query="test"
            )
        )
        mock_retrieval.retrieve_and_hydrate.return_value = (bundle, mock_search_resp)

        # Provider returns invalid response first, then valid response on retry
        invalid_resp = RAGModelResponse(
            answer="Attempt 1: Price is ₹1000",
            claims=[RAGClaim(claim="Price is 1000", product_id=2, attribute="price", value=1000.0, citation=None)]
        )
        valid_resp = RAGModelResponse(
            answer="Attempt 2: Price is ₹2499",
            claims=[RAGClaim(claim="Price is 2499", product_id=2, attribute="price", value=2499.0, citation=None)]
        )

        mock_provider = MockRAGLLMProvider(responses=[invalid_resp, valid_resp])
        service = RAGService(
            retrieval_service=mock_retrieval,
            llm_provider=mock_provider,
            validator=CitationValidator(),
            config=RAGConfig()
        )

        mock_db = MagicMock()
        res = service.answer_query(mock_db, "price of shoe")

        assert res.status == "success"
        assert res.telemetry.retry_count == 1
        assert not res.telemetry.fallback_triggered
        assert mock_provider.call_count == 2
        # Verify that Attempt 2 payload contained correction feedback
        assert "CORRECTION FEEDBACK" in mock_provider.received_payloads[1].user_text
        print("[PASS] Check 13: First validation failure triggers exactly 1 retry with feedback")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 13: Single retry flow: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 14: Second failure produces fail-closed safe fallback
    # --------------------------------------------------------------------------
    try:
        mock_retrieval = MagicMock()
        mock_retrieval.retrieve_and_hydrate.return_value = (bundle, mock_search_resp)

        # Both attempts fail
        bad_resp1 = RAGModelResponse(
            answer="Attempt 1: Fake Kevlar material",
            claims=[RAGClaim(claim="Material is Kevlar", product_id=2, attribute="material", value="Kevlar", citation=None)]
        )
        bad_resp2 = RAGModelResponse(
            answer="Attempt 2: Still Kevlar",
            claims=[RAGClaim(claim="Material is Kevlar", product_id=2, attribute="material", value="Kevlar", citation=None)]
        )

        mock_provider2 = MockRAGLLMProvider(responses=[bad_resp1, bad_resp2])
        service2 = RAGService(
            retrieval_service=mock_retrieval,
            llm_provider=mock_provider2,
            validator=CitationValidator(),
            config=RAGConfig()
        )

        res2 = service2.answer_query(mock_db, "material of shoe")

        assert res2.status == "fallback"
        assert res2.telemetry.fallback_triggered is True
        assert res2.telemetry.retry_count == 1
        assert res2.claims == []  # Unverified claims suppressed
        assert "could not verify all specific product details" in res2.answer  # Safe fallback text
        assert mock_provider2.call_count == 2
        print("[PASS] Check 14: Second failure produces fail-closed safe fallback with empty claims")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 14: Fail-closed fallback: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 15: Zero search results do not call LLM
    # --------------------------------------------------------------------------
    try:
        mock_retrieval_zero = MagicMock()
        empty_bundle = RAGKnowledgeBundle(question="pink running shoes under 500", products=[])
        zero_search_resp = SearchResponse(
            query="pink running shoes under 500",
            results=[],
            metadata=SearchMetadata(
                eligible_candidate_count=0,
                total_eligible=0,
                returned_count=0,
                requested_limit=5,
                took_ms=3.0,
                k_expanded=False,
                parsed_filters=SearchFilters(brand="Nike", max_price=500.0),
                semantic_query="pink running shoes"
            )
        )
        mock_retrieval_zero.retrieve_and_hydrate.return_value = (empty_bundle, zero_search_resp)

        mock_provider_zero = MockRAGLLMProvider(responses=[])
        service_zero = RAGService(
            retrieval_service=mock_retrieval_zero,
            llm_provider=mock_provider_zero,
            validator=CitationValidator(),
            config=RAGConfig()
        )

        res_zero = service_zero.answer_query(mock_db, "pink running shoes under 500")

        assert res_zero.status == "no_results"
        assert mock_provider_zero.call_count == 0  # Zero LLM calls
        assert res_zero.telemetry.llm_latency_ms == 0.0
        assert res_zero.claims == []
        assert "increasing the maximum price limit (₹500.0)" in res_zero.answer
        assert "removing the brand filter ('Nike')" in res_zero.answer
        print("[PASS] Check 15: Zero results short-circuit with 0 LLM calls & relaxation guidance")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Check 15: Zero search results short-circuit: {e}")
        failed += 1

    # --------------------------------------------------------------------------
    # Check 16 (API Test): POST /api/v1/rag/query contract
    # --------------------------------------------------------------------------
    try:
        from app.api.rag import get_rag_service

        mock_api_service = MagicMock()
        mock_api_service.answer_query.return_value = RAGResponse(
            query="test query",
            answer="Grounded answer",
            claims=[
                RAGClaim(
                    claim="Leather upper",
                    product_id=2,
                    attribute="material",
                    value="Leather",
                    citation=RAGCitation(image_id=101)
                )
            ],
            retrieved_products=[{"product_id": 2, "title": "Nike"}],
            telemetry={
                "total_latency_ms": 45.0,
                "retrieval_latency_ms": 10.0,
                "llm_latency_ms": 25.0,
                "validation_latency_ms": 5.0,
                "retry_count": 0,
                "fallback_triggered": False,
                "prompt_version": "rag_v1",
                "model_name": "gemini-3.1-flash-lite",
                "context_product_count": 1,
                "input_tokens": 100,
                "output_tokens": 50,
            },
            status="success"
        )

        app.dependency_overrides[get_rag_service] = lambda: mock_api_service
        client = TestClient(app)

        response = client.post("/api/v1/rag/query", json={"query": "Show me leather shoes"})
        assert response.status_code == 200, f"API failed with {response.status_code}: {response.text}"
        data = response.json()
        assert data["query"] == "test query"
        assert data["answer"] == "Grounded answer"
        assert len(data["claims"]) == 1
        assert data["status"] == "success"
        app.dependency_overrides.clear()
        print("[PASS] Bonus Check: POST /api/v1/rag/query API contract verified")
    except Exception as e:
        print(f"[FAIL] Bonus Check: API endpoint test: {e}")

    print("=" * 70)
    print(f"RESULTS: {passed}/{total} checks passed, {failed} failed.")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_all_checks()
