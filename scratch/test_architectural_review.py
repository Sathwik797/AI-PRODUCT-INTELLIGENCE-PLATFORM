"""Phase 07 Architectural Review: Verification of Final Eligibility Guard across all Core 6 constraints.

Scenario:
Query: "black Nike running shoes size 10 between ₹3000 and ₹5000"
8 candidate products evaluated:
- Candidate 1: FULLY ELIGIBLE (survives)
- Candidate 2: Brand violation (Adidas) -> ELIMINATED
- Candidate 3: Category violation (Books) -> ELIMINATED
- Candidate 4: Min price violation (2500 < 3000) -> ELIMINATED
- Candidate 5: Max price violation (7500 > 5000) -> ELIMINATED
- Candidate 6: Color violation in AI metadata JSON (blue != black) -> ELIMINATED
- Candidate 7: Size violation in AI metadata JSON (8 != 10) -> ELIMINATED
- Candidate 8: Status violation (INACTIVE) -> ELIMINATED

Confirms ONLY Candidate 1 survives.
"""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.ai_generation import AIGeneration
from app.models.category import Category
from app.models.product import Product
from app.models.product_metadata import ProductMetadata
from app.schemas.search import SearchFilters, SearchQuery
from app.search.eligibility_guard import FinalEligibilityGuard


def run_review_verification():
    db: Session = SessionLocal()
    created_product_ids = []
    created_category_ids = []
    created_generation_ids = []
    created_metadata_ids = []

    try:
        print("=" * 70)
        print("PHASE 07 ARCHITECTURAL REVIEW: FINAL ELIGIBILITY GUARD VERIFICATION")
        print("=" * 70)

        # 1. Setup Categories
        cat_shoes = db.query(Category).filter(Category.name == "Shoes").first()
        if not cat_shoes:
            cat_shoes = Category(name="Shoes")
            db.add(cat_shoes)
            db.commit()
            db.refresh(cat_shoes)
            created_category_ids.append(cat_shoes.id)

        cat_books = db.query(Category).filter(Category.name == "Books").first()
        if not cat_books:
            cat_books = Category(name="Books")
            db.add(cat_books)
            db.commit()
            db.refresh(cat_books)
            created_category_ids.append(cat_books.id)

        ts = int(time.time_ns()) % 1000000

        # Helper to create product with AI metadata
        def create_fixture_product(title, brand, cat_id, price, color_val, size_val, status="ACTIVE"):
            p = Product(
                title=title,
                description=f"Description for {title}",
                brand=brand,
                sku=f"REV-{title[:5]}-{ts}-{len(created_product_ids)}",
                price=price,
                category_id=cat_id,
                status=status
            )
            db.add(p)
            db.commit()
            db.refresh(p)
            created_product_ids.append(p.id)

            # Create AI generation with actual nested JSON structure
            gen = AIGeneration(
                product_id=p.id,
                generation_number=1,
                status="completed",
                output={
                    "attributes": {
                        "color": {
                            "type": "text",
                            "value": color_val,
                            "evidence": {"explanation": f"Color is {color_val}"},
                            "confidence": 1.0
                        },
                        "size": {
                            "type": "text",
                            "value": str(size_val),
                            "evidence": {"explanation": f"Size is {size_val}"},
                            "confidence": 1.0
                        }
                    }
                },
                acceptance_state={"attributes": "accepted"}
            )
            db.add(gen)
            db.commit()
            db.refresh(gen)
            created_generation_ids.append(gen.id)

            # Link ProductMetadata
            pm = ProductMetadata(
                product_id=p.id,
                current_generation_id=gen.id
            )
            db.add(pm)
            db.commit()
            db.refresh(pm)
            created_metadata_ids.append(pm.id)
            return p

        # Candidate 1: Fully Eligible
        c1 = create_fixture_product("Nike Air Max Valid", "Nike", cat_shoes.id, 4500.0, "white, black, red", "10")

        # Candidate 2: Brand violation (Adidas != Nike)
        c2 = create_fixture_product("Adidas Ultra Invalid Brand", "Adidas", cat_shoes.id, 4500.0, "black", "10")

        # Candidate 3: Category violation (Books != Shoes)
        c3 = create_fixture_product("Nike Book Invalid Cat", "Nike", cat_books.id, 4500.0, "black", "10")

        # Candidate 4: Min price violation (2500 < 3000)
        c4 = create_fixture_product("Nike Cheap Invalid MinPrice", "Nike", cat_shoes.id, 2500.0, "black", "10")

        # Candidate 5: Max price violation (7500 > 5000)
        c5 = create_fixture_product("Nike Elite Invalid MaxPrice", "Nike", cat_shoes.id, 7500.0, "black", "10")

        # Candidate 6: Color violation (blue != black)
        c6 = create_fixture_product("Nike Blue Invalid Color", "Nike", cat_shoes.id, 4500.0, "blue, white", "10")

        # Candidate 7: Size violation (8 != 10)
        c7 = create_fixture_product("Nike Size8 Invalid Size", "Nike", cat_shoes.id, 4500.0, "black", "8")

        # Candidate 8: Status violation (INACTIVE)
        c8 = create_fixture_product("Nike Inactive Invalid Status", "Nike", cat_shoes.id, 4500.0, "black", "10", status="INACTIVE")

        candidate_pool = [c1.id, c2.id, c3.id, c4.id, c5.id, c6.id, c7.id, c8.id]

        # Construct SearchQuery with all Core 6 constraints
        search_query = SearchQuery(
            original_query="black Nike running shoes size 10 between ₹3000 and ₹5000",
            semantic_query="running shoes",
            filters=SearchFilters(
                brand="Nike",
                category="Shoes",
                category_id=cat_shoes.id,
                color="Black",
                size="10",
                min_price=3000.0,
                max_price=5000.0
            )
        )

        guard = FinalEligibilityGuard()
        eligible_products, _ = guard.filter_eligible_candidates(db, candidate_pool, search_query)

        print(f"\nEvaluated {len(candidate_pool)} candidates against query filters:")
        print(f"  Brand: Nike")
        print(f"  Category ID: {cat_shoes.id} (Shoes)")
        print(f"  Price: 3000.0 - 5000.0")
        print(f"  Color: Black")
        print(f"  Size: 10")
        print(f"\nResults surviving Final Eligibility Guard: {list(eligible_products.keys())}")

        assert len(eligible_products) == 1, f"Expected exactly 1 surviving product, got {len(eligible_products)}"
        assert c1.id in eligible_products, f"Candidate 1 (ID {c1.id}) was expected to survive"
        assert c2.id not in eligible_products, "Candidate 2 (brand violation) should have been eliminated!"
        assert c3.id not in eligible_products, "Candidate 3 (category violation) should have been eliminated!"
        assert c4.id not in eligible_products, "Candidate 4 (min_price violation) should have been eliminated!"
        assert c5.id not in eligible_products, "Candidate 5 (max_price violation) should have been eliminated!"
        assert c6.id not in eligible_products, "Candidate 6 (color violation) should have been eliminated!"
        assert c7.id not in eligible_products, "Candidate 7 (size violation) should have been eliminated!"
        assert c8.id not in eligible_products, "Candidate 8 (status violation) should have been eliminated!"

        print("\n--> [SUCCESS] Final Eligibility Guard strictly eliminated all 7 constraint-violating candidates.")
        print(f"    Only the fully eligible Product {c1.id} ('{c1.title}') survived.")
        return True

    finally:
        # Teardown
        try:
            for mid in created_metadata_ids:
                m = db.query(ProductMetadata).filter(ProductMetadata.id == mid).first()
                if m:
                    db.delete(m)
            for gid in created_generation_ids:
                g = db.query(AIGeneration).filter(AIGeneration.id == gid).first()
                if g:
                    db.delete(g)
            for pid in created_product_ids:
                p = db.query(Product).filter(Product.id == pid).first()
                if p:
                    db.delete(p)
            for cid in created_category_ids:
                c = db.query(Category).filter(Category.id == cid).first()
                if c:
                    db.delete(c)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


if __name__ == "__main__":
    ok = run_review_verification()
    sys.exit(0 if ok else 1)
