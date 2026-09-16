"""Test Suite: EmbeddingTextBuilder & Content Hashing.

Phase 06 Verification: Tests 1-9
- Deterministic text compilation
- Field ordering
- Collection normalization and sorting
- Meaningful ordering (e.g. Dimensions L x W x H)
- Exclusion of operational fields (SKU, IDs, price, timestamps)
- Inclusion of semantic numeric fields (measurements, ranges, dimensions)
- Inclusion of accepted/modified AI metadata
- Exclusion of rejected/unaccepted AI metadata
- SHA-256 content hashing
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from types import SimpleNamespace
from app.ai.embedding_text_builder import EmbeddingTextBuilder, compute_content_hash


def test_embedding_text_builder_deterministic_and_ordering():
    print("\n--- TEST 1: EmbeddingTextBuilder Deterministic Output & Ordering ---")
    product = SimpleNamespace(
        id=42,
        title="Nike Air Force 1 '07",
        brand="Nike",
        description="Classic basketball shoe featuring crisp leather and bold details.",
        category=SimpleNamespace(name="Shoes"),
        price=110.0,
        sku="NK-AF1-001",
        status="active"
    )

    accepted_metadata = {
        "tags": ["Footwear", "sneakers", "Retro", "footwear"],
        "keywords": ["athletic", "streetwear", "basketball shoes", "air force"],
        "attributes": {
            "material": {"type": "text", "value": "Leather"},
            "color": {"type": "text", "value": "White / Pure Platinum"},
            "closure": "Lace-Up",
            "weight": {"type": "measurement", "value": 420.5, "unit": "g"}
        }
    }

    doc1 = EmbeddingTextBuilder.build(product, accepted_metadata)
    doc2 = EmbeddingTextBuilder.build(product, accepted_metadata)

    assert doc1 == doc2, "Builder output must be 100% deterministic"

    expected_lines = [
        "Title: Nike Air Force 1 '07",
        "Brand: Nike",
        "Category: Shoes",
        "Description: Classic basketball shoe featuring crisp leather and bold details.",
        "Attributes: closure: Lace-Up; color: White / Pure Platinum; material: Leather; weight: 420.5 g",
        "Tags: footwear, retro, sneakers",
        "Keywords: air force, athletic, basketball shoes, streetwear"
    ]
    assert doc1 == "\n".join(expected_lines), f"Doc format mismatch:\n{doc1}"
    print("[PASS] Deterministic output, fixed section ordering, and sorted collections verified.")


def test_dimensions_and_semantic_numbers():
    print("\n--- TEST 2: Structured Dimensions and Numeric Attributes ---")
    product = SimpleNamespace(
        id=10,
        title="Travel Backpack 35L",
        brand="North Ridge",
        category=SimpleNamespace(name="Bags"),
        description="Durable outdoor backpack."
    )

    accepted_metadata = {
        "attributes": {
            "dimensions": {
                "type": "dimensions",
                "length": 55.0,
                "width": 35.0,
                "height": 25.0
            },
            "volume_range": {
                "type": "range",
                "min": 30.0,
                "max": 35.0
            },
            "capacity": {
                "type": "measurement",
                "value": 35,
                "unit": "L"
            },
            "waterproof": True
        }
    }

    doc = EmbeddingTextBuilder.build(product, accepted_metadata)

    assert "dimensions: L: 55.0 x W: 35.0 x H: 25.0" in doc, "Dimensions L x W x H order must be preserved"
    assert "capacity: 35 L" in doc, "Measurement must include numeric value and unit"
    assert "volume_range: 30.0 - 35.0" in doc, "Range format must be min - max"
    assert "waterproof: true" in doc, "Booleans must be lowercased"
    print("[PASS] Dimensions (L x W x H), ranges, measurements, and booleans verified.")


def test_exclusion_of_operational_and_unaccepted_fields():
    print("\n--- TEST 3: Exclusion of Operational Fields and Unaccepted AI Metadata ---")
    product = SimpleNamespace(
        id=999,
        title="Gaming Monitor 27-inch",
        brand="Acer",
        sku="SKU-MONITOR-999",
        price=299.99,
        inventory_count=45,
        status="in_stock",
        description="Fast 144Hz IPS display."
    )

    # Note: accepted_metadata only receives accepted/modified fields.
    # Rejected fields or evidence are NOT passed into accepted_metadata.
    accepted_metadata = {
        "tags": ["electronics", "gaming"],
        # Notice: price, sku, confidence, evidence are absent
    }

    doc = EmbeddingTextBuilder.build(product, accepted_metadata, category_name="Electronics")

    assert "999" not in doc, "Product ID must be excluded"
    assert "SKU-MONITOR-999" not in doc, "SKU must be excluded"
    assert "299.99" not in doc, "Price must be excluded"
    assert "45" not in doc, "Inventory count must be excluded"
    assert "in_stock" not in doc, "Operational status must be excluded"
    assert "confidence" not in doc, "Confidence must be excluded"
    assert "evidence" not in doc, "Evidence explanations must be excluded"
    print("[PASS] Operational fields and unaccepted metadata strictly excluded.")


def test_sha256_content_hashing():
    print("\n--- TEST 4: SHA-256 Content Hashing & Sensitivity ---")
    p1 = SimpleNamespace(title="Running Shoes", brand="Adidas", description="Trail runner")
    p2 = SimpleNamespace(title="Running Shoes", brand="Adidas", description="Trail runner")
    p3 = SimpleNamespace(title="Running Shoes", brand="Adidas", description="Trail runner modified")

    doc1 = EmbeddingTextBuilder.build(p1)
    doc2 = EmbeddingTextBuilder.build(p2)
    doc3 = EmbeddingTextBuilder.build(p3)

    hash1 = compute_content_hash(doc1)
    hash2 = compute_content_hash(doc2)
    hash3 = compute_content_hash(doc3)

    assert hash1 == hash2, "Identical documents must yield identical SHA-256 hash"
    assert hash1 != hash3, "Semantic change must alter the SHA-256 hash"
    assert len(hash1) == 64, "SHA-256 hash must be 64-character hex string"
    print("[PASS] SHA-256 content hashing verified.")


def main():
    print("=" * 60)
    print("RUNNING EMBEDDING TEXT BUILDER & HASHING TEST SUITE")
    print("=" * 60)
    test_embedding_text_builder_deterministic_and_ordering()
    test_dimensions_and_semantic_numbers()
    test_exclusion_of_operational_and_unaccepted_fields()
    test_sha256_content_hashing()
    print("=" * 60)
    print("ALL 4 TEXT BUILDER TEST SUITES PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    main()
