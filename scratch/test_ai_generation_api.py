import sys
sys.path.insert(0, ".")

from datetime import datetime, timezone
import json
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.models
from app.models.category import Category
from app.models.product import Product
from app.models.ai_generation import AIGeneration
from app.models.product_metadata import ProductMetadata

from app.db.dependencies import get_db
from app.main import app
import app.api.ai_generation as api_module
from app.api.ai_generation import process_generation_task
from app.repositories.ai_generation_repository import AIGenerationRepository
from app.services.ai_generation_service import (
    AIGenerationService,
    AIGenerationServiceError,
    ProductNotFoundError,
)

print("=" * 70)
print("RUNNING PHASE 05 STEP 6: ASYNC AI GENERATION & REST API TEST SUITE")
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


# Setup test SQLite database and TestClient
from sqlalchemy.pool import StaticPool

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
Base.metadata.create_all(bind=test_engine)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)
test_db = TestSession()


def seed_test_data():
    cat = Category(name="Test Category")
    test_db.add(cat)
    test_db.commit()
    test_db.refresh(cat)

    prod = Product(
        title="Test Headphones",
        description="Noise canceling wireless",
        brand="BrandX",
        sku="SKU-API-001",
        price=199.99,
        category_id=cat.id
    )
    test_db.add(prod)
    test_db.commit()
    test_db.refresh(prod)
    return prod


# 1. POST creates exactly one pending generation and schedules background processing with exact ID
def test_1_post_creates_pending_generation():
    prod = seed_test_data()

    # Patch process_generation_task so TestClient does not execute processing inline
    with patch("app.api.ai_generation.process_generation_task") as mock_bg_task:
        response = client.post(f"/products/{prod.id}/ai/generate")

        assert response.status_code == 202
        data = response.json()
        assert "generation_id" in data
        assert data["product_id"] == prod.id
        assert data["status"] == "pending"

        gen_id = data["generation_id"]

        # Verify background task was scheduled with the exact created generation_id
        mock_bg_task.assert_called_once_with(gen_id)

        # Verify exactly ONE generation record exists in the database with status='pending'
        gen_repo = AIGenerationRepository()
        gens = gen_repo.get_by_product(test_db, prod.id)
        assert len(gens) == 1
        assert gens[0].id == gen_id
        assert gens[0].status == "pending"

run_test("1. POST creates exactly one pending generation & schedules background task", test_1_post_creates_pending_generation)


# 2. POST for non-existent product returns 404
def test_2_post_missing_product_returns_404():
    with patch("app.api.ai_generation.process_generation_task") as mock_bg_task:
        response = client.post("/products/999999/ai/generate")
        assert response.status_code == 404
        assert "Product with id 999999 not found" in response.json()["detail"]
        mock_bg_task.assert_not_called()

run_test("2. POST for missing product returns HTTP 404", test_2_post_missing_product_returns_404)


# 3. GET returns pending generation correctly
def test_3_get_pending_generation():
    gen = AIGeneration(
        product_id=1,
        generation_number=10,
        status="pending",
        model_name="gemini-2.5-flash",
        prompt_version="v1",
        schema_version="v1"
    )
    test_db.add(gen)
    test_db.commit()
    test_db.refresh(gen)

    response = client.get(f"/products/1/ai/generations/{gen.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["generation_id"] == gen.id
    assert data["product_id"] == 1
    assert data["status"] == "pending"
    assert data["output"] is None
    assert data["error_message"] is None

run_test("3. GET returns pending generation status and null output", test_3_get_pending_generation)


# 4. GET returns processing generation correctly
def test_4_get_processing_generation():
    gen = AIGeneration(
        product_id=1,
        generation_number=11,
        status="processing",
        started_at=datetime.now(timezone.utc)
    )
    test_db.add(gen)
    test_db.commit()
    test_db.refresh(gen)

    response = client.get(f"/products/1/ai/generations/{gen.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["generation_id"] == gen.id
    assert data["status"] == "processing"
    assert data["started_at"] is not None

run_test("4. GET returns processing generation correctly", test_4_get_processing_generation)


# 5. GET returns completed generation and structured output
def test_5_get_completed_generation():
    output_payload = {
        "title": {"value": "Sample Headset"},
        "brand": {"value": "SampleBrand"}
    }
    acceptance_payload = {"title": "pending", "brand": "pending"}

    gen = AIGeneration(
        product_id=1,
        generation_number=12,
        status="completed",
        output=output_payload,
        acceptance_state=acceptance_payload,
        processing_time=1.234,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc)
    )
    test_db.add(gen)
    test_db.commit()
    test_db.refresh(gen)

    response = client.get(f"/products/1/ai/generations/{gen.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["generation_id"] == gen.id
    assert data["status"] == "completed"
    assert data["output"] == output_payload
    assert data["acceptance_state"] == acceptance_payload
    assert data["processing_time"] == 1.234

run_test("5. GET returns completed generation with output and acceptance_state", test_5_get_completed_generation)


# 6. GET returns failed generation and error_message
def test_6_get_failed_generation():
    gen = AIGeneration(
        product_id=1,
        generation_number=13,
        status="failed",
        error_message="Gemini API rate limit reached",
        processing_time=0.456,
        completed_at=datetime.now(timezone.utc)
    )
    test_db.add(gen)
    test_db.commit()
    test_db.refresh(gen)

    response = client.get(f"/products/1/ai/generations/{gen.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["generation_id"] == gen.id
    assert data["status"] == "failed"
    assert data["error_message"] == "Gemini API rate limit reached"
    assert data["output"] is None

run_test("6. GET returns failed generation with error_message", test_6_get_failed_generation)


# 7. GET rejects product/generation mismatch with 404
def test_7_get_product_mismatch_returns_404():
    gen = AIGeneration(
        product_id=1,
        generation_number=14,
        status="completed"
    )
    test_db.add(gen)
    test_db.commit()
    test_db.refresh(gen)

    # Ask for generation owned by product 1 using product 999
    response = client.get(f"/products/999/ai/generations/{gen.id}")
    assert response.status_code == 404
    assert "Generation not found" in response.json()["detail"]

run_test("7. GET rejects product ID mismatch with HTTP 404", test_7_get_product_mismatch_returns_404)


# 8. GET for non-existent generation returns 404
def test_8_get_missing_generation_returns_404():
    response = client.get("/products/1/ai/generations/999999")
    assert response.status_code == 404
    assert "Generation not found" in response.json()["detail"]

run_test("8. GET for missing generation returns HTTP 404", test_8_get_missing_generation_returns_404)


# 9. Background adapter receives exact generation_id, uses fresh SessionLocal(), and calls process_generation()
def test_9_background_adapter_lifecycle():
    mock_session = MagicMock()
    mock_service = MagicMock()

    with patch("app.api.ai_generation.SessionLocal", return_value=mock_session), \
         patch("app.api.ai_generation.ai_generation_service", mock_service):

        process_generation_task(777)

        # Verified: service.process_generation called with generation_id 777 and the fresh session
        mock_service.process_generation.assert_called_once_with(mock_session, 777)

        # Verified: session closed cleanly in finally block
        mock_session.close.assert_called_once()

run_test("9. Background adapter uses isolated SessionLocal() and closes in finally", test_9_background_adapter_lifecycle)


# 10. Background adapter closes session even when process_generation raises an exception
def test_10_background_adapter_closes_on_error():
    mock_session = MagicMock()
    mock_service = MagicMock()
    mock_service.process_generation.side_effect = RuntimeError("Crash during generation")

    with patch("app.api.ai_generation.SessionLocal", return_value=mock_session), \
         patch("app.api.ai_generation.ai_generation_service", mock_service):

        process_generation_task(888)

        # Verify session closed despite exception
        mock_session.close.assert_called_once()

run_test("10. Background adapter guarantees session close even on unexpected error", test_10_background_adapter_closes_on_error)


# 11. Processing idempotency: already processing/completed/failed generations are not processed twice
def test_11_processing_idempotency():
    gen_completed = AIGeneration(product_id=1, generation_number=20, status="completed")
    gen_failed = AIGeneration(product_id=1, generation_number=21, status="failed")
    gen_processing = AIGeneration(product_id=1, generation_number=22, status="processing")

    test_db.add_all([gen_completed, gen_failed, gen_processing])
    test_db.commit()

    mock_provider = MagicMock()
    service = AIGenerationService(
        product_repository=MagicMock(),
        image_repository=MagicMock(),
        category_repository=MagicMock(),
        ai_generation_repository=AIGenerationRepository(),
        product_metadata_repository=MagicMock(),
        provider=mock_provider
    )

    # Attempt to process completed generation
    res_c = service.process_generation(test_db, gen_completed.id)
    assert res_c.status == "completed"
    mock_provider.generate_product_metadata.assert_not_called()

    # Attempt to process failed generation
    res_f = service.process_generation(test_db, gen_failed.id)
    assert res_f.status == "failed"
    mock_provider.generate_product_metadata.assert_not_called()

    # Attempt to process already processing generation
    res_p = service.process_generation(test_db, gen_processing.id)
    assert res_p.status == "processing"
    mock_provider.generate_product_metadata.assert_not_called()

run_test("11. Processing idempotency: completed/failed/processing generations skip execution", test_11_processing_idempotency)


# 12. Architectural boundaries in router: no direct Gemini SDK calls or AI context building
def test_12_router_architectural_boundaries():
    assert "google" not in api_module.__dict__, "Google SDK found in api router module!"
    assert "genai" not in api_module.__dict__, "genai found in api router module!"
    assert "AIProductContextBuilder" not in api_module.__dict__, "ContextBuilder found in api router module!"
    assert "GeminiProvider" not in api_module.__dict__, "GeminiProvider found in api router module!"

run_test("12. Router contains zero direct Gemini SDK or AI context construction logic", test_12_router_architectural_boundaries)


print("=" * 70)
print(f"FINAL STEP 6 RESULTS: {passed} PASSED, {failed} FAILED")
print("=" * 70)

if failed > 0:
    sys.exit(1)
