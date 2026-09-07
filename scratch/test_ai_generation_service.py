import sys
sys.path.insert(0, ".")

import json
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.models  # Register all models: Category, Product, Image, AIGeneration, ProductMetadata
from app.models.category import Category
from app.models.product import Product
from app.models.image import Image
from app.models.ai_generation import AIGeneration
from app.models.product_metadata import ProductMetadata

from app.repositories.product_repository import ProductRepository
from app.repositories.image_repository import ImageRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.ai_generation_repository import AIGenerationRepository
from app.repositories.product_metadata_repository import ProductMetadataRepository

import app.services.ai_generation_service as ags_module
from app.services.ai_generation_service import (
    AIGenerationService,
    AIGenerationServiceError,
    ProductNotFoundError,
    AIGenerationExecutionError,
    PROMPT_VERSION,
    SCHEMA_VERSION,
)
from app.ai.gemini_provider import (
    AIProductContext,
    GeminiConfig,
    GeminiProvider,
    GeminiProviderError,
    GeminiResponseValidationError,
)
from app.schemas.ai_metadata import AIProductMetadata

print("=" * 70)
print("RUNNING PHASE 05 STEP 5: AI GENERATION SERVICE TEST SUITE")
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


# Setup in-memory SQLite database for isolated ORM integration tests
def create_test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


# Sample valid AIProductMetadata dictionary
VALID_METADATA_DICT = {
    "title": {
        "type": "text",
        "value": "Sony WH-1000XM5 Wireless Headphones",
        "confidence": 0.98,
        "evidence": {
            "source": {"type": "image", "image_id": 1},
            "explanation": "Headphone model text on headband"
        }
    },
    "description": {
        "type": "text",
        "value": "Industry leading noise canceling headphones with auto NC optimizer.",
        "confidence": 0.92,
        "evidence": {
            "source": {"type": "seller"},
            "explanation": "Seller specifications"
        }
    },
    "brand": {
        "type": "text",
        "value": "Sony",
        "confidence": 0.99,
        "evidence": {
            "source": {"type": "image", "image_id": 1},
            "explanation": "Sony logo embossed on ear cup"
        }
    },
    "category": {
        "value": {
            "recommended_category_id": 10,
            "recommended_category_name": "Audio",
            "proposed_category": "Noise Canceling Headphones"
        },
        "confidence": 0.95,
        "evidence": {
            "source": {"type": "image", "image_id": 1},
            "explanation": "Over-ear headphone design"
        }
    },
    "tags": ["audio", "wireless", "noise-canceling"],
    "keywords": ["sony headphones", "over ear bluetooth"],
    "attributes": {
        "color": {
            "type": "text",
            "value": "Silver",
            "confidence": 0.96,
            "evidence": {
                "source": {"type": "image", "image_id": 1},
                "explanation": "Visual ear cup color"
            }
        }
    }
}


def make_mock_provider(return_val=None, raise_exc=None):
    mock_provider = MagicMock()
    mock_provider.config = GeminiConfig(api_key="test-key", model_name="gemini-2.5-flash")
    if raise_exc:
        mock_provider.generate_product_metadata.side_effect = raise_exc
    else:
        valid_obj = AIProductMetadata.model_validate(return_val or VALID_METADATA_DICT)
        mock_provider.generate_product_metadata.return_value = valid_obj
    return mock_provider


def seed_product(db, sku="TEST-SKU-001"):
    category = Category(name="Electronics")
    db.add(category)
    db.commit()
    db.refresh(category)

    product = Product(
        title="Original Seller Title",
        description="Seller product description.",
        brand="Seller Brand",
        sku=sku,
        price=399.99,
        status="ACTIVE",
        category_id=category.id
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    image1 = Image(
        product_id=product.id,
        image_url="uploads/test1.jpg",
        filename="test1.jpg",
        mime_type="image/jpeg",
        file_size=1024,
        width=800,
        height=600,
        display_order=1
    )
    db.add(image1)
    db.commit()
    db.refresh(image1)

    return product, category, [image1]


# 1. Successful generation lifecycle: pending -> processing -> completed
def test_1_successful_generation_lifecycle():
    db = create_test_db()
    product, _, _ = seed_product(db, "SKU-LIFECYCLE")

    mock_provider = make_mock_provider()
    service = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=ProductMetadataRepository(),
        provider=mock_provider
    )

    gen = service.generate(db, product.id)

    assert gen.id is not None
    assert gen.status == "completed"
    assert gen.output is not None
    assert gen.output["title"]["value"] == "Sony WH-1000XM5 Wireless Headphones"
    assert gen.processing_time is not None and gen.processing_time >= 0.0
    assert gen.started_at is not None
    assert gen.completed_at is not None
    assert gen.error_message is None
    assert gen.model_name == "gemini-2.5-flash"
    assert gen.prompt_version == PROMPT_VERSION
    assert gen.schema_version == SCHEMA_VERSION

    # Verify ProductMetadata active draft pointer was updated
    meta_repo = ProductMetadataRepository()
    meta = meta_repo.get_by_product_id(db, product.id)
    assert meta is not None
    assert meta.current_generation_id == gen.id

run_test("1. Successful generation: pending -> processing -> completed with output & pointer updated", test_1_successful_generation_lifecycle)


# 2. First generation receives generation_number = 1
def test_2_first_generation_number():
    db = create_test_db()
    product, _, _ = seed_product(db, "SKU-GEN-1")

    service = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=ProductMetadataRepository(),
        provider=make_mock_provider()
    )

    gen = service.generate(db, product.id)
    assert gen.generation_number == 1

run_test("2. First generation attempt receives generation_number = 1", test_2_first_generation_number)


# 3. Subsequent generation increments monotonically (1 -> 2 -> 3)
def test_3_subsequent_generation_increment():
    db = create_test_db()
    product, _, _ = seed_product(db, "SKU-GEN-INC")

    service = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=ProductMetadataRepository(),
        provider=make_mock_provider()
    )

    gen1 = service.generate(db, product.id)
    gen2 = service.generate(db, product.id)
    gen3 = service.generate(db, product.id)

    assert gen1.generation_number == 1
    assert gen2.generation_number == 2
    assert gen3.generation_number == 3

    meta = ProductMetadataRepository().get_by_product_id(db, product.id)
    assert meta.current_generation_id == gen3.id

run_test("3. Subsequent generations increment monotonically (1 -> 2 -> 3)", test_3_subsequent_generation_increment)


# 4. Failed generation records failure and does NOT update current_generation_id
def test_4_failed_generation_pointer_untouched():
    db = create_test_db()
    product, _, _ = seed_product(db, "SKU-FAIL-POINTER")

    failing_provider = make_mock_provider(raise_exc=GeminiProviderError("Model quota exceeded"))
    service = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=ProductMetadataRepository(),
        provider=failing_provider
    )

    try:
        service.generate(db, product.id)
        raise AssertionError("Should have raised AIGenerationExecutionError")
    except AIGenerationExecutionError as e:
        assert "Model quota exceeded" in str(e)

    # Verify generation row was marked 'failed'
    gen_repo = AIGenerationRepository()
    latest_gen = gen_repo.get_latest_for_product(db, product.id)
    assert latest_gen is not None
    assert latest_gen.status == "failed"
    assert "Model quota exceeded" in latest_gen.error_message
    assert latest_gen.completed_at is not None
    assert latest_gen.processing_time is not None

    # Verify ProductMetadata pointer was NEVER created or moved
    meta = ProductMetadataRepository().get_by_product_id(db, product.id)
    assert meta is None or meta.current_generation_id is None

run_test("4. Failed generation becomes 'failed' with error_message and leaves pointer untouched", test_4_failed_generation_pointer_untouched)


# 5. GeminiProviderError is handled correctly
def test_5_gemini_provider_error_handling():
    db = create_test_db()
    product, _, _ = seed_product(db, "SKU-PROV-ERR")

    failing_provider = make_mock_provider(raise_exc=GeminiProviderError("Network connection reset"))
    service = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=ProductMetadataRepository(),
        provider=failing_provider
    )

    try:
        service.generate(db, product.id)
        raise AssertionError("Should have raised AIGenerationExecutionError")
    except AIGenerationExecutionError as e:
        assert isinstance(e, AIGenerationServiceError)
        assert "Network connection reset" in str(e)

run_test("5. GeminiProviderError is translated to AIGenerationExecutionError", test_5_gemini_provider_error_handling)


# 6. Pydantic validation failure is handled correctly
def test_6_pydantic_validation_failure_handling():
    db = create_test_db()
    product, _, _ = seed_product(db, "SKU-VAL-ERR")

    val_provider = make_mock_provider(raise_exc=GeminiResponseValidationError("Schema confidence constraint violated"))
    service = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=ProductMetadataRepository(),
        provider=val_provider
    )

    try:
        service.generate(db, product.id)
        raise AssertionError("Should have raised AIGenerationExecutionError")
    except AIGenerationExecutionError as e:
        assert "Schema confidence constraint violated" in str(e)

    gen = AIGenerationRepository().get_latest_for_product(db, product.id)
    assert gen.status == "failed"
    assert "Schema confidence constraint violated" in gen.error_message

run_test("6. Pydantic validation failure recorded as failed generation with diagnostics", test_6_pydantic_validation_failure_handling)


# 7. Unexpected exception is handled correctly
def test_7_unexpected_exception_handling():
    db = create_test_db()
    product, _, _ = seed_product(db, "SKU-UNEXP-ERR")

    unexp_provider = make_mock_provider(raise_exc=ZeroDivisionError("Unexpected math bug"))
    service = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=ProductMetadataRepository(),
        provider=unexp_provider
    )

    try:
        service.generate(db, product.id)
        raise AssertionError("Should have raised AIGenerationExecutionError")
    except AIGenerationExecutionError as e:
        assert "Unexpected math bug" in str(e)

    gen = AIGenerationRepository().get_latest_for_product(db, product.id)
    assert gen.status == "failed"
    assert "Unexpected math bug" in gen.error_message

run_test("7. Unexpected exceptions caught, recorded as failed, and re-raised cleanly", test_7_unexpected_exception_handling)


# 8. Missing product raises ProductNotFoundError before creating generation
def test_8_missing_product_raises_not_found():
    db = create_test_db()
    service = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=ProductMetadataRepository(),
        provider=make_mock_provider()
    )

    try:
        service.generate(db, product_id=999999)
        raise AssertionError("Should have raised ProductNotFoundError")
    except ProductNotFoundError as e:
        assert "Product with id 999999 not found" in str(e)
        assert isinstance(e, ValueError)

    # Verify no generation records were created for non-existent product
    gens = AIGenerationRepository().get_by_product(db, 999999)
    assert len(gens) == 0

run_test("8. Missing product raises ProductNotFoundError without creating generation row", test_8_missing_product_raises_not_found)


# 9. AIProductContextBuilder is called with domain data
def test_9_context_builder_called():
    db = create_test_db()
    product, category, images = seed_product(db, "SKU-BUILDER-CALL")

    mock_builder = MagicMock()
    mock_builder.build_context.return_value = AIProductContext(product_id=product.id)

    service = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=ProductMetadataRepository(),
        provider=make_mock_provider(),
        context_builder=mock_builder
    )

    service.generate(db, product.id)

    mock_builder.build_context.assert_called_once()
    call_kwargs = mock_builder.build_context.call_args[1]
    assert call_kwargs["product"].id == product.id
    assert len(call_kwargs["images"]) == 1

run_test("9. AIProductContextBuilder is invoked with domain entities", test_9_context_builder_called)


# 10. GeminiProvider receives AIProductContext, not SQLAlchemy Product
def test_10_provider_receives_pure_context():
    db = create_test_db()
    product, _, _ = seed_product(db, "SKU-PURE-CTX")

    mock_provider = make_mock_provider()
    service = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=ProductMetadataRepository(),
        provider=mock_provider
    )

    service.generate(db, product.id)

    mock_provider.generate_product_metadata.assert_called_once()
    received_arg = mock_provider.generate_product_metadata.call_args[0][0]

    assert isinstance(received_arg, AIProductContext)
    assert not isinstance(received_arg, Product)
    assert received_arg.product_id == product.id

run_test("10. GeminiProvider receives pure AIProductContext DTO, never SQLAlchemy Product", test_10_provider_receives_pure_context)


# 11. Acceptance state initializes correctly for all top-level AI metadata fields
def test_11_acceptance_state_initialization():
    db = create_test_db()
    product, _, _ = seed_product(db, "SKU-ACCEPT-STATE")

    service = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=ProductMetadataRepository(),
        provider=make_mock_provider()
    )

    gen = service.generate(db, product.id)

    acc = gen.acceptance_state
    assert isinstance(acc, dict)
    for expected_field in ["title", "description", "brand", "category", "tags", "keywords", "attributes"]:
        assert expected_field in acc
        assert acc[expected_field] == "pending"

run_test("11. Acceptance state initializes correctly as 'pending' for all top-level fields", test_11_acceptance_state_initialization)


# 12. Successful regeneration moves current_generation_id to the newest completed generation
def test_12_regeneration_advances_pointer():
    db = create_test_db()
    product, _, _ = seed_product(db, "SKU-ADVANCE-PTR")

    service = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=ProductMetadataRepository(),
        provider=make_mock_provider()
    )

    gen1 = service.generate(db, product.id)
    meta1 = ProductMetadataRepository().get_by_product_id(db, product.id)
    assert meta1.current_generation_id == gen1.id

    gen2 = service.generate(db, product.id)
    meta2 = ProductMetadataRepository().get_by_product_id(db, product.id)
    assert meta2.current_generation_id == gen2.id
    assert gen2.id != gen1.id

run_test("12. Successful regeneration advances current_generation_id to the newest generation", test_12_regeneration_advances_pointer)


# 13. Failed regeneration preserves the previous current_generation_id
def test_13_failed_regeneration_preserves_previous_pointer():
    db = create_test_db()
    product, _, _ = seed_product(db, "SKU-PRESERVE-PTR")

    good_provider = make_mock_provider()
    service_good = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=ProductMetadataRepository(),
        provider=good_provider
    )

    gen1 = service_good.generate(db, product.id)
    meta1 = ProductMetadataRepository().get_by_product_id(db, product.id)
    assert meta1.current_generation_id == gen1.id

    # Now run a failed second generation attempt
    bad_provider = make_mock_provider(raise_exc=GeminiProviderError("API connection timeout"))
    service_bad = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=ProductMetadataRepository(),
        provider=bad_provider
    )

    try:
        service_bad.generate(db, product.id)
    except AIGenerationExecutionError:
        pass

    # Verify gen2 is failed
    gen2 = AIGenerationRepository().get_latest_for_product(db, product.id)
    assert gen2.generation_number == 2
    assert gen2.status == "failed"

    # Verify ProductMetadata pointer STILL points to gen1!
    meta2 = ProductMetadataRepository().get_by_product_id(db, product.id)
    assert meta2.current_generation_id == gen1.id

run_test("13. Failed regeneration preserves previous valid current_generation_id pointer", test_13_failed_regeneration_preserves_previous_pointer)


# 14. No FastAPI HTTPException exists inside the service
def test_14_no_fastapi_http_exception():
    assert "fastapi" not in ags_module.__dict__, "FastAPI imported in ai_generation_service module!"
    assert "HTTPException" not in ags_module.__dict__, "HTTPException found in ai_generation_service module!"

run_test("14. Zero FastAPI or HTTPException dependencies in ai_generation_service", test_14_no_fastapi_http_exception)


# 15. No direct google.genai import exists inside the service
def test_15_no_direct_google_genai_import():
    with open("app/services/ai_generation_service.py", "r", encoding="utf-8") as f:
        src = f.read()
    assert "google.genai" not in src, "Direct google.genai import found in ai_generation_service.py!"
    assert "genai" not in ags_module.__dict__, "genai found in module dict!"

run_test("15. Zero direct google.genai imports in ai_generation_service", test_15_no_direct_google_genai_import)


# 16. Final success transaction coordinates generation update and product_metadata in single atomic transaction
def test_16_coordinated_final_success_transaction():
    db = create_test_db()
    product, _, _ = seed_product(db, "SKU-COORD-TX")

    gen_repo = AIGenerationRepository()
    meta_repo = ProductMetadataRepository()

    # Track commit calls on the Session
    original_commit = db.commit
    commit_count = 0
    def spy_commit():
        nonlocal commit_count
        commit_count += 1
        return original_commit()
    db.commit = spy_commit

    service = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=gen_repo,
        product_metadata_repository=meta_repo,
        provider=make_mock_provider()
    )

    service.generate(db, product.id)

    # 1st commit: create pending generation
    # 2nd commit: update to processing
    # 3rd commit: coordinated final success transaction (atomic commit of completed generation + product_metadata)
    assert commit_count == 3

    # Verify both entities are committed and consistent
    gen = gen_repo.get_latest_for_product(db, product.id)
    meta = meta_repo.get_by_product_id(db, product.id)
    assert gen.status == "completed"
    assert meta.current_generation_id == gen.id

run_test("16. Final success transaction coordinates generation completion and pointer atomically", test_16_coordinated_final_success_transaction)


# 17. Failure path invokes db.rollback() before persisting status='failed'
def test_17_rollback_before_failed_state_committed():
    db = create_test_db()
    product, _, _ = seed_product(db, "SKU-ROLLBACK-TEST")

    rollback_called = False
    original_rollback = db.rollback
    def spy_rollback():
        nonlocal rollback_called
        rollback_called = True
        return original_rollback()
    db.rollback = spy_rollback

    # Provider that fails during generation
    failing_provider = make_mock_provider(raise_exc=RuntimeError("Provider exploded"))

    service = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=ProductMetadataRepository(),
        provider=failing_provider
    )

    try:
        service.generate(db, product.id)
        raise AssertionError("Should have raised AIGenerationExecutionError")
    except AIGenerationExecutionError as e:
        assert "Provider exploded" in str(e)

    # 1. Verify db.rollback() was explicitly called before recording the failed state
    assert rollback_called is True, "db.rollback() was NOT called in failure handler!"

    # 2. Verify the generation status was safely updated and persisted to 'failed'
    gen = AIGenerationRepository().get_latest_for_product(db, product.id)
    assert gen.status == "failed"
    assert "Provider exploded" in gen.error_message
    assert gen.completed_at is not None
    assert gen.processing_time is not None

    # 3. Verify ProductMetadata was untouched
    meta = ProductMetadataRepository().get_by_product_id(db, product.id)
    assert meta is None

run_test("17. Failure path calls db.rollback() before updating status to 'failed'", test_17_rollback_before_failed_state_committed)


# 18. Secondary failure to persist failure state logs critical error and preserves original exception
def test_18_failure_to_record_failed_state_does_not_mask_original_error():
    db = create_test_db()
    product, _, _ = seed_product(db, "SKU-SEC-FAIL")

    failing_provider = make_mock_provider(raise_exc=ValueError("Original domain error"))

    mock_gen_repo = MagicMock()
    # First call create() succeeds
    mock_gen_record = AIGeneration(id=55, product_id=product.id, generation_number=1, status="pending")
    mock_gen_repo.create.return_value = mock_gen_record
    mock_gen_repo.get_by_id.return_value = mock_gen_record
    mock_gen_repo.get_next_generation_number.return_value = 1
    # update() succeeds for pending -> processing, but fails when trying to persist 'failed'
    update_calls = 0
    def side_effect_update(db, gen, commit=True):
        nonlocal update_calls
        update_calls += 1
        if update_calls > 1:
            raise ConnectionError("Database crashed while writing failed status")
        return gen
    mock_gen_repo.update.side_effect = side_effect_update

    service = AIGenerationService(
        product_repository=ProductRepository(),
        image_repository=ImageRepository(),
        category_repository=CategoryRepository(),
        ai_generation_repository=mock_gen_repo,
        product_metadata_repository=ProductMetadataRepository(),
        provider=failing_provider
    )

    with patch("app.services.ai_generation_service.logger.critical") as mock_crit_log:
        try:
            service.generate(db, product.id)
            raise AssertionError("Should have raised AIGenerationExecutionError")
        except AIGenerationExecutionError as e:
            # Original exception must NOT be masked by the database ConnectionError!
            assert "Original domain error" in str(e)
            assert isinstance(e.__cause__, ValueError)

        # Verify critical log was emitted
        mock_crit_log.assert_called_once()
        assert "Failed to record failure status" in mock_crit_log.call_args[0][0]

run_test("18. Secondary DB failure when recording 'failed' logs critical error and does not mask original error", test_18_failure_to_record_failed_state_does_not_mask_original_error)


print("=" * 70)
print(f"FINAL STEP 5/6 SERVICE RESULTS: {passed} PASSED, {failed} FAILED")
print("=" * 70)

if failed > 0:
    sys.exit(1)
