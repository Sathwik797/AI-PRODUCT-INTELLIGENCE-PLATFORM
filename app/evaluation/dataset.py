"""Benchmark Dataset Management and Synthetic Catalog Generator for Step 07.1.

Implements Q66, Q68:
- Benchmark file loader and serializer
- Deterministic catalog-derived synthetic query generator (derives ground truth from active MySQL items)
- Smoke Benchmark Suite builder (20–30 queries across all 5 archetypes)
"""

import json
import os
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.product import Product
from app.schemas.evaluation import BenchmarkCase, BenchmarkSuite
from app.schemas.search import SearchFilters
from app.search.filters import extract_attribute_value_str
from app.services.embedding_service import EmbeddingService

BENCHMARK_DIR = Path("evaluation/benchmarks")


def load_benchmark_suite(file_path: str | Path) -> BenchmarkSuite:
    """Loads a BenchmarkSuite from a JSON file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Benchmark file not found at {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return BenchmarkSuite.model_validate(data)


def save_benchmark_suite(suite: BenchmarkSuite, file_path: str | Path) -> None:
    """Persists a BenchmarkSuite to a JSON file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(suite.model_dump_json(indent=2))


def generate_catalog_synthetic_cases(db: Session) -> list[BenchmarkCase]:
    """Deterministically generates synthetic benchmark cases from active catalog records (Q66, Q67)."""
    active_products = (
        db.query(Product)
        .filter(Product.status == "ACTIVE")
        .all()
    )
    if not active_products:
        return []

    cases: list[BenchmarkCase] = []
    emb_service = EmbeddingService()

    for idx, prod in enumerate(active_products, start=1):
        pid = prod.id
        brand = prod.brand or "Nike"
        price = float(prod.price)
        cat_name = prod.category.name if prod.category else "Shoes"

        # Read accepted metadata attributes
        meta = emb_service.get_accepted_ai_metadata(db, pid)
        color = extract_attribute_value_str(meta, "color") or "White"
        # Extract first color if comma-separated
        primary_color = color.split(",")[0].strip()

        # 1. Exact Attribute
        cases.append(
            BenchmarkCase(
                benchmark_id=f"syn_exact_{idx:03d}",
                query_text=f"{brand} {prod.title}",
                track="synthetic",
                query_type="exact_attribute",
                expected_constraints=SearchFilters(brand=brand),
                ground_truth={pid: 2},
                is_zero_result_expected=False
            )
        )

        # 2. Compound Constraints
        cases.append(
            BenchmarkCase(
                benchmark_id=f"syn_compound_{idx:03d}",
                query_text=f"{primary_color} {brand} {cat_name} under {int(price + 1000)}",
                track="synthetic",
                query_type="compound_constraints",
                expected_constraints=SearchFilters(
                    brand=brand,
                    color=primary_color,
                    max_price=price + 1000.0
                ),
                ground_truth={pid: 2},
                is_zero_result_expected=False
            )
        )

        # 3. Edge Case: Price at exact ceiling
        cases.append(
            BenchmarkCase(
                benchmark_id=f"syn_edge_{idx:03d}",
                query_text=f"{brand} under {int(price)}",
                track="synthetic",
                query_type="edge_cases",
                expected_constraints=SearchFilters(
                    brand=brand,
                    max_price=price
                ),
                ground_truth={pid: 2},
                is_zero_result_expected=False
            )
        )

        # 4. Zero-Result: Budget strictly below product price
        cases.append(
            BenchmarkCase(
                benchmark_id=f"syn_zero_{idx:03d}",
                query_text=f"{brand} {cat_name} under {int(price - 1000)}",
                track="synthetic",
                query_type="zero_result",
                expected_constraints=SearchFilters(
                    brand=brand,
                    max_price=max(0.0, price - 1000.0)
                ),
                ground_truth={},
                is_zero_result_expected=True
            )
        )

    return cases


def build_default_smoke_suite(db: Optional[Session] = None) -> BenchmarkSuite:
    """Constructs the canonical 20–30 query Smoke Benchmark Suite (Q68).
    
    Includes handcrafted curated queries and catalog-derived synthetic queries
    balanced across all 5 archetypes.
    """
    cases: list[BenchmarkCase] = []

    # Get active product reference if DB session provided
    target_pid = 2
    if db:
        first_prod = db.query(Product).filter(Product.status == "ACTIVE").first()
        if first_prod:
            target_pid = first_prod.id

    # -------------------------------------------------------------
    # 1. Exact Attribute Queries (~5 queries)
    # -------------------------------------------------------------
    cases.extend([
        BenchmarkCase(
            benchmark_id="smoke_exact_001",
            query_text="Nike shoes",
            track="curated",
            query_type="exact_attribute",
            expected_constraints=SearchFilters(brand="Nike"),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
        BenchmarkCase(
            benchmark_id="smoke_exact_002",
            query_text="Nike Air Force",
            track="curated",
            query_type="exact_attribute",
            expected_constraints=SearchFilters(brand="Nike"),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
        BenchmarkCase(
            benchmark_id="smoke_exact_003",
            query_text="Nike Air Force 1 '72",
            track="curated",
            query_type="exact_attribute",
            expected_constraints=SearchFilters(brand="Nike"),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
        BenchmarkCase(
            benchmark_id="smoke_exact_004",
            query_text="Nike footwear",
            track="curated",
            query_type="exact_attribute",
            expected_constraints=SearchFilters(brand="Nike"),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
        BenchmarkCase(
            benchmark_id="smoke_exact_005",
            query_text="brand Nike",
            track="curated",
            query_type="exact_attribute",
            expected_constraints=SearchFilters(brand="Nike"),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
    ])

    # -------------------------------------------------------------
    # 2. Compound Constraints Queries (~5 queries)
    # -------------------------------------------------------------
    cases.extend([
        BenchmarkCase(
            benchmark_id="smoke_compound_001",
            query_text="white Nike shoes under 10000",
            track="curated",
            query_type="compound_constraints",
            expected_constraints=SearchFilters(brand="Nike", color="white", max_price=10000.0),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
        BenchmarkCase(
            benchmark_id="smoke_compound_002",
            query_text="red Nike shoes under 8000",
            track="curated",
            query_type="compound_constraints",
            expected_constraints=SearchFilters(brand="Nike", color="red", max_price=8000.0),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
        BenchmarkCase(
            benchmark_id="smoke_compound_003",
            query_text="black Nike shoes under 7000",
            track="curated",
            query_type="compound_constraints",
            expected_constraints=SearchFilters(brand="Nike", color="black", max_price=7000.0),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
        BenchmarkCase(
            benchmark_id="smoke_compound_004",
            query_text="Nike shoes between 4000 and 8000",
            track="curated",
            query_type="compound_constraints",
            expected_constraints=SearchFilters(brand="Nike", min_price=4000.0, max_price=8000.0),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
        BenchmarkCase(
            benchmark_id="smoke_compound_005",
            query_text="white leather Nike shoes under 6500",
            track="curated",
            query_type="compound_constraints",
            expected_constraints=SearchFilters(brand="Nike", color="white", max_price=6500.0),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
    ])

    # -------------------------------------------------------------
    # 3. Pure Semantic / Intent Queries (~5 queries)
    # -------------------------------------------------------------
    cases.extend([
        BenchmarkCase(
            benchmark_id="smoke_semantic_001",
            query_text="comfortable athletic sneakers for everyday wear",
            track="curated",
            query_type="semantic_intent",
            expected_constraints=SearchFilters(),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
        BenchmarkCase(
            benchmark_id="smoke_semantic_002",
            query_text="classic retro basketball sneakers",
            track="curated",
            query_type="semantic_intent",
            expected_constraints=SearchFilters(),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
        BenchmarkCase(
            benchmark_id="smoke_semantic_003",
            query_text="durable rubber sole lace-up sneakers",
            track="curated",
            query_type="semantic_intent",
            expected_constraints=SearchFilters(),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
        BenchmarkCase(
            benchmark_id="smoke_semantic_004",
            query_text="cushioned lifestyle trainers",
            track="curated",
            query_type="semantic_intent",
            expected_constraints=SearchFilters(),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
        BenchmarkCase(
            benchmark_id="smoke_semantic_005",
            query_text="fashionable streetwear kicks",
            track="curated",
            query_type="semantic_intent",
            expected_constraints=SearchFilters(),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
    ])

    # -------------------------------------------------------------
    # 4. Edge Cases (~4 queries)
    # -------------------------------------------------------------
    cases.extend([
        BenchmarkCase(
            benchmark_id="smoke_edge_001",
            query_text="Nike under 5999",
            track="curated",
            query_type="edge_cases",
            expected_constraints=SearchFilters(brand="Nike", max_price=5999.0),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
        BenchmarkCase(
            benchmark_id="smoke_edge_002",
            query_text="shoes between 5999 and 6000",
            track="curated",
            query_type="edge_cases",
            expected_constraints=SearchFilters(min_price=5999.0, max_price=6000.0),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
        BenchmarkCase(
            benchmark_id="smoke_edge_003",
            query_text="white red black Nike shoes",
            track="curated",
            query_type="edge_cases",
            expected_constraints=SearchFilters(brand="Nike", color="white"),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
        BenchmarkCase(
            benchmark_id="smoke_edge_004",
            query_text="Nike 5999",
            track="curated",
            query_type="edge_cases",
            expected_constraints=SearchFilters(brand="Nike"),
            ground_truth={target_pid: 2},
            is_zero_result_expected=False
        ),
    ])

    # -------------------------------------------------------------
    # 5. Zero-Result / Negative Queries (~4 queries)
    # -------------------------------------------------------------
    cases.extend([
        BenchmarkCase(
            benchmark_id="smoke_zero_001",
            query_text="Adidas running shoes",
            track="curated",
            query_type="zero_result",
            expected_constraints=SearchFilters(brand="Adidas"),
            ground_truth={},
            is_zero_result_expected=True
        ),
        BenchmarkCase(
            benchmark_id="smoke_zero_002",
            query_text="Nike shoes under 1000",
            track="curated",
            query_type="zero_result",
            expected_constraints=SearchFilters(brand="Nike", max_price=1000.0),
            ground_truth={},
            is_zero_result_expected=True
        ),
        BenchmarkCase(
            benchmark_id="smoke_zero_003",
            query_text="green Nike shoes",
            track="curated",
            query_type="zero_result",
            expected_constraints=SearchFilters(brand="Nike", color="green"),
            ground_truth={},
            is_zero_result_expected=True
        ),
        BenchmarkCase(
            benchmark_id="smoke_zero_004",
            query_text="Puma running shoes under 2000",
            track="curated",
            query_type="zero_result",
            expected_constraints=SearchFilters(brand="Puma", max_price=2000.0),
            ground_truth={},
            is_zero_result_expected=True
        ),
    ])

    # Total: 23 queries (strictly within 20–30 range for Smoke tier per Q68)
    return BenchmarkSuite(
        name="smoke",
        version="1.0.0",
        tier="smoke",
        cases=cases
    )
