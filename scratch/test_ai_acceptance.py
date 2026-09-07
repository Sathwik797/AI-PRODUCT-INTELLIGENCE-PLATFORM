"""Standalone Test Suite for Phase 05 – Step 7: AI Metadata Acceptance & Seller Review.

Verifies:
1. Accept All workflow (canonical fields updated, non-canonical in acceptance_state only).
2. Category fallback safety when AI does not provide an existing category ID.
3. Accept Selected workflow (accept, modify with custom text, reject, pending).
4. applied_fields strictly excludes non-canonical fields (tags, keywords, attributes).
5. Immutability of AIGeneration.output across accept and modify actions.
6. Automatic transition of 'accepted' to 'modified' when seller updates product manually.
7. Business and constraint validation (title length, description length, valid category ID).
8. State guards (rejecting review on pending/failed/non-existent generations).
9. Atomic rollback on database failure.
10. REST API endpoints (GET current, POST accept-all, POST review).
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))

from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
import app.models
from app.models.category import Category
from app.models.product import Product
from app.models.ai_generation import AIGeneration
from app.models.product_metadata import ProductMetadata
from app.db.dependencies import get_db
from app.main import app

from app.repositories.product_repository import ProductRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.ai_generation_repository import AIGenerationRepository
from app.repositories.product_metadata_repository import ProductMetadataRepository
from app.schemas.ai_generation import (
    FieldReviewAction,
    FieldReviewDecision,
)
from app.schemas.product import ProductUpdate
from app.services.ai_acceptance_service import (
    AIAcceptanceService,
    AcceptanceValidationError,
    InvalidGenerationStateError,
    NoActiveGenerationError,
    ProductNotFoundError,
)
from app.services.product_service import ProductService

print("=" * 75)
print("RUNNING PHASE 05 STEP 7: AI METADATA ACCEPTANCE & SELLER REVIEW TEST SUITE")
print("=" * 75)

# Setup in-memory SQLite engine
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

product_repo = ProductRepository()
category_repo = CategoryRepository()
ai_gen_repo = AIGenerationRepository()
metadata_repo = ProductMetadataRepository()

acceptance_service = AIAcceptanceService(
    product_repository=product_repo,
    ai_generation_repository=ai_gen_repo,
    product_metadata_repository=metadata_repo,
    category_repository=category_repo,
)

product_service = ProductService(
    product_repository=product_repo,
    category_repository=category_repo,
    ai_acceptance_service=acceptance_service,
)

passed = 0
failed = 0

def run_test(name, fn):
    global passed, failed
    # Re-create tables per test
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        fn()
        print(f"[PASS] {name}")
        passed += 1
    except Exception as e:
        print(f"[FAIL] {name} -> {e}")
        import traceback
        traceback.print_exc()
        failed += 1


def seed_base_data(db):
    cat1 = Category(id=1, name="Electronics")
    cat2 = Category(id=2, name="Audio")
    db.add_all([cat1, cat2])
    db.commit()

    product = Product(
        id=10,
        title="Original Draft Title",
        description="Original seller draft description",
        brand="Original Brand",
        sku="SKU-1001",
        price=99.99,
        status="ACTIVE",
        category_id=1,
    )
    db.add(product)
    db.commit()

    ai_output = {
        "title": {
            "type": "text",
            "value": "AI Enhanced Wireless Headphones Pro",
            "confidence": 0.95,
            "evidence": {"source": {"type": "image", "image_id": 1}, "explanation": "Branding observed"},
        },
        "description": {
            "type": "text",
            "value": "High-fidelity noise-cancelling wireless headphones with 40-hour battery life.",
            "confidence": 0.92,
            "evidence": {"source": {"type": "seller"}, "explanation": "Feature list"},
        },
        "brand": {
            "type": "text",
            "value": "AudioTech",
            "confidence": 0.98,
            "evidence": {"source": {"type": "image", "image_id": 1}, "explanation": "Front logo"},
        },
        "category": {
            "value": {
                "recommended_category_id": 2,
                "recommended_category_name": "Audio",
                "proposed_category": "Headphones",
            },
            "confidence": 0.96,
            "evidence": {"source": {"type": "inferred"}, "explanation": "Form factor"},
        },
        "tags": ["audio", "wireless", "headphones"],
        "keywords": ["bluetooth headphones", "noise cancelling", "over-ear"],
        "attributes": {
            "color": {
                "type": "text",
                "value": "Matte Black",
                "confidence": 0.99,
                "evidence": {"source": {"type": "image", "image_id": 1}, "explanation": "Visual inspection"},
            }
        },
    }

    initial_acc = {
        "title": "pending",
        "description": "pending",
        "brand": "pending",
        "category": "pending",
        "tags": "pending",
        "keywords": "pending",
        "attributes": "pending",
    }

    generation = AIGeneration(
        id=100,
        product_id=10,
        generation_number=1,
        status="completed",
        output=ai_output,
        acceptance_state=initial_acc,
        model_name="gemini-2.5-flash",
        processing_time=1.25,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(generation)
    db.commit()

    metadata = ProductMetadata(
        product_id=10,
        current_generation_id=100,
    )
    db.add(metadata)
    db.commit()

    return product, generation


# ==============================================================================
# TEST CASES
# ==============================================================================

def test_accept_all_successful():
    db = TestingSessionLocal()
    try:
        seed_base_data(db)
        res = acceptance_service.accept_all(db, product_id=10)

        assert res.product_id == 10
        assert res.generation_id == 100

        # Canonical Product columns updated
        product = product_repo.get_by_id(db, 10)
        assert product.title == "AI Enhanced Wireless Headphones Pro"
        assert product.description == "High-fidelity noise-cancelling wireless headphones with 40-hour battery life."
        assert product.brand == "AudioTech"
        assert product.category_id == 2  # Updated to recommended category 2

        # Non-AI fields untouched
        assert product.sku == "SKU-1001"
        assert product.price == 99.99
        assert product.status == "ACTIVE"

        # applied_fields contains only canonical columns
        assert set(res.applied_fields) == {"title", "description", "brand", "category_id"}
        assert "tags" not in res.applied_fields
        assert "keywords" not in res.applied_fields
        assert "attributes" not in res.applied_fields

        # All fields in acceptance_state marked accepted
        gen = ai_gen_repo.get_by_id(db, 100)
        for k, v in gen.acceptance_state.items():
            assert v == "accepted", f"Field {k} should be accepted"
    finally:
        db.close()


def test_accept_all_category_fallback_when_no_id():
    db = TestingSessionLocal()
    try:
        product, gen = seed_base_data(db)
        # Modify category in AI output to have no recommended_category_id
        output = dict(gen.output)
        output["category"] = {
            "value": {
                "recommended_category_id": None,
                "recommended_category_name": None,
                "proposed_category": "Novel Category",
            },
            "confidence": 0.8,
            "evidence": {"source": {"type": "inferred"}, "explanation": "New category"},
        }
        gen.output = output
        db.commit()

        res = acceptance_service.accept_all(db, product_id=10)

        # Category was NOT overwritten (remains initial cat 1)
        db_product = product_repo.get_by_id(db, 10)
        assert db_product.category_id == 1
        assert "category_id" not in res.applied_fields

        # Category marked rejected in acceptance_state
        gen_updated = ai_gen_repo.get_by_id(db, 100)
        assert gen_updated.acceptance_state["category"] == "rejected"
        assert gen_updated.acceptance_state["title"] == "accepted"
    finally:
        db.close()


def test_accept_selected_decisions():
    db = TestingSessionLocal()
    try:
        seed_base_data(db)
        decisions = {
            "title": FieldReviewDecision(action=FieldReviewAction.ACCEPT),
            "description": FieldReviewDecision(
                action=FieldReviewAction.MODIFY,
                modified_value="Seller customized description."
            ),
            "brand": FieldReviewDecision(action=FieldReviewAction.REJECT),
            "category": FieldReviewDecision(action=FieldReviewAction.ACCEPT),
            "tags": FieldReviewDecision(action=FieldReviewAction.ACCEPT),
            "keywords": FieldReviewDecision(action=FieldReviewAction.REJECT),
        }

        res = acceptance_service.review_selected(db, product_id=10, decisions=decisions)

        product = product_repo.get_by_id(db, 10)
        assert product.title == "AI Enhanced Wireless Headphones Pro"  # accepted
        assert product.description == "Seller customized description."  # modified
        assert product.brand == "Original Brand"  # rejected -> untouched
        assert product.category_id == 2  # accepted

        # applied_fields contains only updated canonical columns
        assert set(res.applied_fields) == {"title", "description", "category_id"}
        assert "tags" not in res.applied_fields
        assert "keywords" not in res.applied_fields

        # acceptance_state verification
        gen = ai_gen_repo.get_by_id(db, 100)
        assert gen.acceptance_state["title"] == "accepted"
        assert gen.acceptance_state["description"] == "modified"
        assert gen.acceptance_state["brand"] == "rejected"
        assert gen.acceptance_state["category"] == "accepted"
        assert gen.acceptance_state["tags"] == "accepted"
        assert gen.acceptance_state["keywords"] == "rejected"
        assert gen.acceptance_state["attributes"] == "pending"  # unmentioned
    finally:
        db.close()


def test_output_immutability():
    db = TestingSessionLocal()
    try:
        seed_base_data(db)
        gen_before = ai_gen_repo.get_by_id(db, 100)
        original_output = dict(gen_before.output)

        decisions = {
            "title": FieldReviewDecision(action=FieldReviewAction.MODIFY, modified_value="Overridden Title"),
            "description": FieldReviewDecision(action=FieldReviewAction.MODIFY, modified_value="Overridden Description"),
        }
        acceptance_service.review_selected(db, product_id=10, decisions=decisions)

        gen_after = ai_gen_repo.get_by_id(db, 100)
        # Output must be 100% untouched
        assert gen_after.output == original_output
        assert gen_after.output["title"]["value"] == "AI Enhanced Wireless Headphones Pro"
        # Only acceptance_state reflects modified
        assert gen_after.acceptance_state["title"] == "modified"
    finally:
        db.close()


def test_manual_product_update_transitions_accepted_to_modified():
    db = TestingSessionLocal()
    try:
        seed_base_data(db)
        # 1. Accept all
        acceptance_service.accept_all(db, product_id=10)
        gen = ai_gen_repo.get_by_id(db, 100)
        assert gen.acceptance_state["title"] == "accepted"
        assert gen.acceptance_state["description"] == "accepted"

        # 2. Seller performs manual product update via ProductService
        product_service.update(
            db=db,
            product_id=10,
            product_update=ProductUpdate(title="Manual Seller Retitle")
        )

        # 3. Verify Product updated
        product = product_repo.get_by_id(db, 10)
        assert product.title == "Manual Seller Retitle"

        # 4. Verify acceptance_state transitioned title to 'modified'
        db.refresh(gen)
        assert gen.acceptance_state["title"] == "modified"
        assert gen.acceptance_state["description"] == "accepted"
    finally:
        db.close()


def test_validation_errors():
    db = TestingSessionLocal()
    try:
        seed_base_data(db)

        # 1. Empty title
        try:
            acceptance_service.review_selected(
                db,
                product_id=10,
                decisions={"title": FieldReviewDecision(action=FieldReviewAction.MODIFY, modified_value="   ")}
            )
            assert False, "Should raise AcceptanceValidationError"
        except AcceptanceValidationError as e:
            assert "non-empty string" in str(e)

        # 2. Title > 255 chars
        try:
            acceptance_service.review_selected(
                db,
                product_id=10,
                decisions={"title": FieldReviewDecision(action=FieldReviewAction.MODIFY, modified_value="A" * 256)}
            )
            assert False, "Should raise AcceptanceValidationError"
        except AcceptanceValidationError as e:
            assert "exceeds maximum length of 255" in str(e)

        # 3. Description > 1000 chars
        try:
            acceptance_service.review_selected(
                db,
                product_id=10,
                decisions={"description": FieldReviewDecision(action=FieldReviewAction.MODIFY, modified_value="D" * 1001)}
            )
            assert False, "Should raise AcceptanceValidationError"
        except AcceptanceValidationError as e:
            assert "exceeds maximum length of 1000" in str(e)

        # 4. Non-existent category ID
        try:
            acceptance_service.review_selected(
                db,
                product_id=10,
                decisions={"category": FieldReviewDecision(action=FieldReviewAction.MODIFY, modified_value=9999)}
            )
            assert False, "Should raise AcceptanceValidationError"
        except AcceptanceValidationError as e:
            assert "Category with ID 9999 does not exist" in str(e)

        # 5. Missing modified_value when action is modify
        try:
            acceptance_service.review_selected(
                db,
                product_id=10,
                decisions={"title": FieldReviewDecision(action=FieldReviewAction.MODIFY, modified_value=None)}
            )
            assert False, "Should raise AcceptanceValidationError"
        except AcceptanceValidationError as e:
            assert "modified_value is mandatory" in str(e)

        # 6. Unknown field name
        try:
            acceptance_service.review_selected(
                db,
                product_id=10,
                decisions={"invalid_field": FieldReviewDecision(action=FieldReviewAction.ACCEPT)}
            )
            assert False, "Should raise AcceptanceValidationError"
        except AcceptanceValidationError as e:
            assert "Invalid field name" in str(e)
    finally:
        db.close()


def test_state_guards():
    db = TestingSessionLocal()
    try:
        product, gen = seed_base_data(db)

        # 1. Pending generation cannot be reviewed
        gen.status = "pending"
        db.commit()

        try:
            acceptance_service.accept_all(db, product_id=10)
            assert False, "Should raise InvalidGenerationStateError"
        except InvalidGenerationStateError as e:
            assert "in 'pending' state" in str(e)

        # 2. Non-existent product
        try:
            acceptance_service.accept_all(db, product_id=999)
            assert False, "Should raise ProductNotFoundError"
        except ProductNotFoundError:
            pass

        # 3. Product with no active generation
        meta = metadata_repo.get_by_product_id(db, 10)
        db.delete(meta)
        db.commit()

        try:
            acceptance_service.accept_all(db, product_id=10)
            assert False, "Should raise NoActiveGenerationError"
        except NoActiveGenerationError:
            pass
    finally:
        db.close()


def test_api_get_current_endpoint():
    db = TestingSessionLocal()
    try:
        seed_base_data(db)
    finally:
        db.close()

    res = client.get("/products/10/ai/current")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["product_id"] == 10
    assert data["generation_id"] == 100
    assert data["status"] == "completed"
    assert "title" in data["output"]
    assert data["acceptance_state"]["title"] == "pending"


def test_api_accept_all_endpoint():
    db = TestingSessionLocal()
    try:
        seed_base_data(db)
    finally:
        db.close()

    res = client.post("/products/10/ai/accept-all")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["product_id"] == 10
    assert data["generation_id"] == 100
    assert set(data["applied_fields"]) == {"title", "description", "brand", "category_id"}
    assert data["acceptance_state"]["title"] == "accepted"
    assert data["product"]["title"] == "AI Enhanced Wireless Headphones Pro"


def test_api_review_endpoint():
    db = TestingSessionLocal()
    try:
        seed_base_data(db)
    finally:
        db.close()

    payload = {
        "decisions": {
            "title": {"action": "accept"},
            "description": {"action": "modify", "modified_value": "API modified description"},
            "brand": {"action": "reject"},
            "tags": {"action": "accept"},
        }
    }
    res = client.post("/products/10/ai/review", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert set(data["applied_fields"]) == {"title", "description"}
    assert data["acceptance_state"]["title"] == "accepted"
    assert data["acceptance_state"]["description"] == "modified"
    assert data["acceptance_state"]["brand"] == "rejected"
    assert data["acceptance_state"]["tags"] == "accepted"
    assert data["product"]["description"] == "API modified description"


def test_api_review_validation_error_endpoint():
    db = TestingSessionLocal()
    try:
        seed_base_data(db)
    finally:
        db.close()

    payload = {
        "decisions": {
            "title": {"action": "modify", "modified_value": "   "},
        }
    }
    res = client.post("/products/10/ai/review", json=payload)
    assert res.status_code == 400
    assert "non-empty string" in res.json()["detail"]


def test_atomic_rollback_on_failure():
    """Verifies that an unhandled database commit failure triggers db.rollback()."""
    db = TestingSessionLocal()
    try:
        seed_base_data(db)
        from unittest.mock import patch

        # Mock db.commit to raise an exception
        with patch.object(db, "commit", side_effect=RuntimeError("Simulated DB commit crash")):
            try:
                acceptance_service.accept_all(db, product_id=10)
                assert False, "Should have raised RuntimeError"
            except RuntimeError as e:
                assert "Simulated DB commit crash" in str(e)

        # Confirm nothing was committed
        product = product_repo.get_by_id(db, 10)
        assert product.title == "Original Draft Title"
        gen = ai_gen_repo.get_by_id(db, 100)
        assert gen.acceptance_state["title"] == "pending"
    finally:
        db.close()


def test_modify_non_canonical_fields():
    """Verifies modifying tags, keywords, and attributes updates acceptance_state but not applied_fields."""
    db = TestingSessionLocal()
    try:
        seed_base_data(db)
        decisions = {
            "tags": FieldReviewDecision(action=FieldReviewAction.MODIFY, modified_value=["pro", "audiophile"]),
            "keywords": FieldReviewDecision(action=FieldReviewAction.MODIFY, modified_value=["over-ear pro"]),
            "attributes": FieldReviewDecision(action=FieldReviewAction.MODIFY, modified_value={"weight": "250g"}),
        }
        res = acceptance_service.review_selected(db, product_id=10, decisions=decisions)

        # applied_fields must be empty because no canonical product columns were changed
        assert res.applied_fields == []

        gen = ai_gen_repo.get_by_id(db, 100)
        assert gen.acceptance_state["tags"] == "modified"
        assert gen.acceptance_state["keywords"] == "modified"
        assert gen.acceptance_state["attributes"] == "modified"
    finally:
        db.close()


def test_pending_action_in_decisions():
    """Verifies that action='pending' keeps the field unreviewed and leaves Product untouched."""
    db = TestingSessionLocal()
    try:
        seed_base_data(db)
        decisions = {
            "title": FieldReviewDecision(action=FieldReviewAction.PENDING),
            "description": FieldReviewDecision(action=FieldReviewAction.ACCEPT),
        }
        res = acceptance_service.review_selected(db, product_id=10, decisions=decisions)

        product = product_repo.get_by_id(db, 10)
        assert product.title == "Original Draft Title"  # untouched
        assert product.description == "High-fidelity noise-cancelling wireless headphones with 40-hour battery life."

        assert res.applied_fields == ["description"]
        gen = ai_gen_repo.get_by_id(db, 100)
        assert gen.acceptance_state["title"] == "pending"
        assert gen.acceptance_state["description"] == "accepted"
    finally:
        db.close()


# Run all tests
run_test("test_accept_all_successful", test_accept_all_successful)
run_test("test_accept_all_category_fallback_when_no_id", test_accept_all_category_fallback_when_no_id)
run_test("test_accept_selected_decisions", test_accept_selected_decisions)
run_test("test_output_immutability", test_output_immutability)
run_test("test_manual_product_update_transitions_accepted_to_modified", test_manual_product_update_transitions_accepted_to_modified)
run_test("test_validation_errors", test_validation_errors)
run_test("test_state_guards", test_state_guards)
run_test("test_atomic_rollback_on_failure", test_atomic_rollback_on_failure)
run_test("test_modify_non_canonical_fields", test_modify_non_canonical_fields)
run_test("test_pending_action_in_decisions", test_pending_action_in_decisions)
run_test("test_api_get_current_endpoint", test_api_get_current_endpoint)
run_test("test_api_accept_all_endpoint", test_api_accept_all_endpoint)
run_test("test_api_review_endpoint", test_api_review_endpoint)
run_test("test_api_review_validation_error_endpoint", test_api_review_validation_error_endpoint)

print("=" * 75)
print(f"STEP 7 TESTS COMPLETE: Passed: {passed}, Failed: {failed}")
print("=" * 75)

if failed > 0:
    sys.exit(1)

