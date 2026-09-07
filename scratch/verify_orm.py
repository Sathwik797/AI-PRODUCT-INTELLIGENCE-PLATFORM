import sys
sys.path.insert(0, ".")

from app.db.database import SessionLocal
from app.repositories.category_repository import CategoryRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.image_repository import ImageRepository
from app.models.product import Product
from app.models.ai_generation import AIGeneration
from app.models.product_metadata import ProductMetadata

db = SessionLocal()
try:
    cat_repo = CategoryRepository()
    prod_repo = ProductRepository()
    img_repo = ImageRepository()

    categories = cat_repo.get_all(db)
    print(f"Categories in DB: {len(categories)}")

    products = prod_repo.get_all(db)
    print(f"Products in DB: {len(products)}")

    if products:
        p = products[0]
        print(f"Sample Product ID {p.id}: {p.title}")
        print(f"  Images count: {len(p.images)}")
        print(f"  AI Generations count: {len(p.ai_generations)}")
        print(f"  Metadata record: {p.metadata_record}")

    # Confirm relationship properties exist on classes
    assert hasattr(Product, "ai_generations")
    assert hasattr(Product, "metadata_record")
    assert hasattr(AIGeneration, "product")
    assert hasattr(ProductMetadata, "product")
    assert hasattr(ProductMetadata, "current_generation")
    print("All relationship assertions PASSED successfully!")
finally:
    db.close()
