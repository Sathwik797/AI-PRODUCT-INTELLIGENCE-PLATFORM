import sys
sys.path.insert(0, ".")

from unittest.mock import MagicMock
import app.ai as ai_pkg
import app.ai.context_builder as cb_module
import app.ai.gemini_provider as gp_module
from app.ai.context_builder import AIProductContextBuilder
from app.ai.gemini_provider import AIImageInput, AIProductContext, GeminiConfig, GeminiProvider

print("=" * 70)
print("RUNNING PHASE 05 STEP 4: AI CONTEXT BUILDER & PRODUCTION PROMPT SUITE")
print("=" * 70)

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


# 1. AIProductContext can be constructed independently of SQLAlchemy
def test_1_independent_context_construction():
    img = AIImageInput(image_id=99, image_bytes=b"raw_bytes", mime_type="image/jpeg", display_order=1, role="front")
    context = AIProductContext(
        product_id=501,
        title="Pure Standalone Title",
        description="Standalone Description",
        brand="StandaloneBrand",
        price=129.99,
        current_category="Audio Equipment",
        available_categories=["Audio Equipment", "Computers", "Accessories"],
        images=[img]
    )

    assert context.product_id == 501
    assert context.title == "Pure Standalone Title"
    assert context.price == 129.99
    assert context.current_category == "Audio Equipment"
    assert context.category_hint == "Audio Equipment"  # Synchronized
    assert len(context.available_categories) == 3
    assert len(context.images) == 1
    assert context.images[0].role == "front"

run_test("1. AIProductContext constructed independently of SQLAlchemy", test_1_independent_context_construction)


# 2. Context builder does not pass SQLAlchemy objects into provider
def test_2_no_sqlalchemy_objects_passed():
    # Simulate ORM objects with duck typing
    mock_category = MagicMock()
    mock_category.id = 5
    mock_category.name = "Wearables"
    mock_category.__class__.__module__ = "app.models.category"
    mock_category.__class__.__name__ = "Category"

    mock_image_1 = MagicMock()
    mock_image_1.id = 11
    mock_image_1.image_url = "uploads/products/1/img1.jpg"
    mock_image_1.mime_type = "image/jpeg"
    mock_image_1.display_order = 2
    mock_image_1.__class__.__module__ = "app.models.image"
    mock_image_1.__class__.__name__ = "Image"

    mock_image_2 = MagicMock()
    mock_image_2.id = 12
    mock_image_2.image_url = "uploads/products/1/img2.png"
    mock_image_2.mime_type = "image/png"
    mock_image_2.display_order = 1
    mock_image_2.__class__.__module__ = "app.models.image"
    mock_image_2.__class__.__name__ = "Image"

    mock_product = MagicMock()
    mock_product.id = 77
    mock_product.title = "Smart Fitness Watch"
    mock_product.description = "Water-resistant GPS fitness tracker."
    mock_product.brand = "FitPulse"
    mock_product.price = 199.50
    mock_product.category = mock_category
    mock_product.images = [mock_image_1, mock_image_2]
    mock_product.__class__.__module__ = "app.models.product"
    mock_product.__class__.__name__ = "Product"

    avail_cats = [mock_category, "Outdoor Gear"]

    context = AIProductContextBuilder.build_context(
        product=mock_product,
        available_categories=avail_cats,
        image_role_overrides={11: "back", 12: "main"}
    )

    # Verify context is pure DTO
    assert isinstance(context, AIProductContext)
    assert not hasattr(context, "__module__") or not context.__module__.startswith("app.models")
    assert context.product_id == 77
    assert context.title == "Smart Fitness Watch"
    assert context.current_category == "Wearables"
    assert context.available_categories == [{"id": 5, "name": "Wearables"}, {"id": None, "name": "Outdoor Gear"}]

    # Verify each image is pure AIImageInput, NOT the mock Image ORM object
    assert len(context.images) == 2
    for img in context.images:
        assert isinstance(img, AIImageInput)
        assert type(img) is AIImageInput
        assert img.__class__.__module__ == "app.ai.gemini_provider"

run_test("2. Context builder does not pass SQLAlchemy objects into provider", test_2_no_sqlalchemy_objects_passed)


# 3. Multiple images retain exact image IDs and display order
def test_3_multiple_images_retain_exact_ids_and_order():
    raw_images = [
        {"id": 303, "image_url": "p3.jpg", "mime_type": "image/jpeg", "display_order": 3},
        {"id": 101, "image_url": "p1.jpg", "mime_type": "image/jpeg", "display_order": 1},
        {"id": 202, "image_url": "p2.png", "mime_type": "image/png", "display_order": 2},
    ]

    context = AIProductContextBuilder.build_context(
        product={"id": 10, "title": "Test Multi-image"},
        images=raw_images,
        image_role_overrides={101: "packaging", 202: "front_detail"}
    )

    # Must be sorted by display_order: 101, 202, 303
    assert [img.image_id for img in context.images] == [101, 202, 303]
    assert context.images[0].role == "packaging"
    assert context.images[1].role == "front_detail"
    assert context.images[2].role is None
    assert context.images[1].mime_type == "image/png"

run_test("3. Multiple images retain exact image IDs, MIME types, and display order", test_3_multiple_images_retain_exact_ids_and_order)


# 4. Seller context is included in multimodal prompt request
def test_4_seller_context_included():
    context = AIProductContext(
        product_id=400,
        title="Ergonomic Office Chair",
        description="High-back mesh chair with lumbar support.",
        brand="ErgoDesk",
        price=349.00
    )
    provider = GeminiProvider(config=GeminiConfig(api_key="dummy"))
    request = provider.build_multimodal_request(context)

    user_text = request["user_text"]
    assert "Seller Title: Ergonomic Office Chair" in user_text
    assert "Seller Description: High-back mesh chair with lumbar support." in user_text
    assert "Seller Brand: ErgoDesk" in user_text
    assert "Product Price: 349.0" in user_text

run_test("4. Seller context is included in multimodal request prompt", test_4_seller_context_included)


# 5. Existing category context is included in multimodal prompt request
def test_5_category_context_included():
    context = AIProductContext(
        product_id=401,
        title="Test Item",
        current_category="Office Furniture",
        available_categories=[
            {"id": 10, "name": "Office Furniture"},
            {"id": 20, "name": "Home Decor"},
            {"id": 30, "name": "Electronics"}
        ]
    )
    provider = GeminiProvider(config=GeminiConfig(api_key="dummy"))
    request = provider.build_multimodal_request(context)

    user_text = request["user_text"]
    assert "Current Category / Hint: Office Furniture" in user_text
    assert 'Available Platform Taxonomy Categories: [{"id": 10, "name": "Office Furniture"}, {"id": 20, "name": "Home Decor"}, {"id": 30, "name": "Electronics"}]' in user_text

run_test("5. Category context is included in multimodal prompt request", test_5_category_context_included)


# 6. Image evidence instructions require exact image_id
def test_6_image_evidence_exact_id_instruction():
    provider = GeminiProvider(config=GeminiConfig(api_key="dummy"))
    prompt = provider.build_system_prompt()

    assert "7. EXACT IMAGE IDENTITY" in prompt
    assert "must include the exact image_id" in prompt or "MUST cite the exact supplied numerical image_id" in prompt
    assert "Never invent or hallucinate image IDs." in prompt

    img = AIImageInput(image_id=789, image_bytes=b"dummy", mime_type="image/jpeg", display_order=1)
    req = provider.build_multimodal_request(AIProductContext(product_id=1, images=[img]))
    assert "NOTE ON IMAGE EVIDENCE: Each image below is uniquely identified by its exact image_id." in req["user_text"]
    assert "image_id=789" in req["user_text"]

run_test("6. Image evidence instructions require exact image_id and forbid invented IDs", test_6_image_evidence_exact_id_instruction)


# 7. Unknown-value behavior is explicitly instructed
def test_7_unknown_value_instructions():
    provider = GeminiProvider(config=GeminiConfig(api_key="dummy"))
    prompt = provider.build_system_prompt()

    assert "4. UNKNOWN VALUES & NO GUESSING" in prompt
    assert "set value = null" in prompt
    assert "set confidence = 0.0" in prompt
    assert "provide an evidence object explaining why it is unknown" in prompt
    assert "Do not guess" in prompt

run_test("7. Unknown-value behavior (null, 0.0, explanatory evidence, no guessing) instructed", test_7_unknown_value_instructions)


# 8. Image/seller/inferred evidence distinctions exist
def test_8_evidence_distinctions():
    provider = GeminiProvider(config=GeminiConfig(api_key="dummy"))
    prompt = provider.build_system_prompt()

    assert "3. GROUNDING & EVIDENCE" in prompt
    assert "- 'image': Information directly supported by the supplied image" in prompt
    assert "- 'seller': Information explicitly supplied by seller/product context" in prompt
    assert "- 'inferred': A genuine inference derived from available evidence" in prompt
    assert "CRITICAL: Never represent inferred information as directly observed visual fact." in prompt

run_test("8. Distinct evidence source types and inference grounding guardrails present", test_8_evidence_distinctions)


# 9. Variant/conflict instructions exist
def test_9_variant_and_conflict_instructions():
    provider = GeminiProvider(config=GeminiConfig(api_key="dummy"))
    prompt = provider.build_system_prompt()

    # Rule 6: Conflict resolution
    assert "6. CONFLICT RESOLUTION" in prompt
    assert "prefer strong, clearly observable visual evidence" in prompt
    assert "legitimate product variant" in prompt

    # Rule 11: Variants
    assert "11. PRODUCT VARIANTS" in prompt
    assert "do not create ProductVariant records" in prompt
    assert "do not assume differences are contradictions without evidence" in prompt

run_test("9. Variant detection and conflict resolution rules explicitly established", test_9_variant_and_conflict_instructions)


# 10. No SQLAlchemy or FastAPI dependency inside AI context or builder
def test_10_no_sqlalchemy_fastapi_dependency():
    # Context builder module
    assert "sqlalchemy" not in cb_module.__dict__, "SQLAlchemy found in context_builder module!"
    assert "fastapi" not in cb_module.__dict__, "FastAPI found in context_builder module!"
    assert "HTTPException" not in cb_module.__dict__, "HTTPException found in context_builder module!"

    # Gemini provider module
    assert "sqlalchemy" not in gp_module.__dict__, "SQLAlchemy found in gemini_provider module!"
    assert "fastapi" not in gp_module.__dict__, "FastAPI found in gemini_provider module!"
    assert "HTTPException" not in gp_module.__dict__, "HTTPException found in gemini_provider module!"

    # AI package exports
    assert hasattr(ai_pkg, "AIProductContextBuilder")
    assert hasattr(ai_pkg, "AIProductContext")
    assert hasattr(ai_pkg, "AIImageInput")
    assert hasattr(ai_pkg, "GeminiProvider")

run_test("10. Zero SQLAlchemy or FastAPI dependencies in AI DTOs and context builder", test_10_no_sqlalchemy_fastapi_dependency)


# 11. No-images behavior
def test_11_no_images_behavior():
    context = AIProductContext(product_id=888, title="Digital E-Book")
    provider = GeminiProvider(config=GeminiConfig(api_key="dummy"))
    req = provider.build_multimodal_request(context)

    assert "No product images provided. Analyze based on seller context alone." in req["user_text"]
    assert len(req["images"]) == 0

    prompt = provider.build_system_prompt()
    assert "13. NO IMAGES BEHAVIOR" in prompt
    assert "generation is still permitted using seller context alone" in prompt
    assert "clearly reduce confidence scores for all visually dependent attributes" in prompt

run_test("11. Generation without images permitted with seller-only grounding and reduced confidence", test_11_no_images_behavior)


# 12. Anti-hallucination and consistency rules
def test_12_anti_hallucination_rules():
    provider = GeminiProvider(config=GeminiConfig(api_key="dummy"))
    prompt = provider.build_system_prompt()

    assert "15. ANTI-HALLUCINATION SAFEGUARDS" in prompt
    assert "Never invent: brand, material, dimensions, specifications" in prompt
    assert "16. INTERNAL CONSISTENCY" in prompt
    assert "Ensure the product receives internally consistent metadata across all fields" in prompt

run_test("12. Anti-hallucination safeguards and internal consistency rules established", test_12_anti_hallucination_rules)


# 13. Category IDs and names are preserved from duck-typed objects and dicts
def test_13_category_ids_and_names_preserved():
    class FakeCategory:
        def __init__(self, cid, cname):
            self.id = cid
            self.name = cname

    raw_cats = [
        FakeCategory(1, "Books"),
        {"id": 3, "name": "Shoes"},
        {"category_id": 7, "category_name": "Clothing"},
        "Electronics"
    ]

    context = AIProductContextBuilder.build_context(
        product={"id": 200, "title": "Nike Shoes"},
        available_categories=raw_cats
    )

    expected = [
        {"id": 1, "name": "Books"},
        {"id": 3, "name": "Shoes"},
        {"id": 7, "name": "Clothing"},
        {"id": None, "name": "Electronics"}
    ]
    assert context.available_categories == expected
    assert context.existing_categories == expected

run_test("13. Category IDs and names preserved from diverse object types", test_13_category_ids_and_names_preserved)


# 14. Multiple categories preserve sequence and deduplicate
def test_14_multiple_categories_preserved_in_order():
    raw_cats = [
        {"id": 1, "name": "Books"},
        {"id": 2, "name": "Electronics"},
        {"id": 3, "name": "Shoes"},
        {"id": 1, "name": "Books"}  # duplicate
    ]

    context = AIProductContextBuilder.build_context(
        product={"id": 201, "title": "Sneaker Item"},
        available_categories=raw_cats
    )

    assert len(context.available_categories) == 3
    assert context.available_categories[0] == {"id": 1, "name": "Books"}
    assert context.available_categories[1] == {"id": 2, "name": "Electronics"}
    assert context.available_categories[2] == {"id": 3, "name": "Shoes"}

run_test("14. Multiple categories preserve order and deduplicate cleanly", test_14_multiple_categories_preserved_in_order)


# 15. System prompt taxonomy matching instructions
def test_15_taxonomy_matching_instructions():
    provider = GeminiProvider(config=GeminiConfig(api_key="dummy"))
    prompt = provider.build_system_prompt()

    assert "8. CATEGORY TAXONOMY MATCHING & CATEGORY OUTPUT REQUIREMENT" in prompt
    assert "authoritative database ID ('id') and name ('name')" in prompt
    assert "category.value MUST NOT be null" in prompt
    assert "Set recommended_category_id to the exact id from the matching taxonomy item" in prompt
    assert "Never invent, hallucinate, or guess a category ID that is not in the supplied taxonomy." in prompt

run_test("15. System prompt instructs authoritative IDs and forbids inventing IDs", test_15_taxonomy_matching_instructions)


# 16. Dual-category design preserved in system prompt
def test_16_dual_category_design_preserved():
    provider = GeminiProvider(config=GeminiConfig(api_key="dummy"))
    prompt = provider.build_system_prompt()

    assert "propose a specific subcategory in 'proposed_category'" in prompt
    assert "recommended_category_id" in prompt
    assert "recommended_category_name" in prompt

run_test("16. Dual-category design (existing match + proposed subcategory) preserved in prompt", test_16_dual_category_design_preserved)


print("=" * 70)
print(f"FINAL STEP 4 RESULTS: {passed} PASSED, {failed} FAILED")
print("=" * 70)

if failed > 0:
    sys.exit(1)
