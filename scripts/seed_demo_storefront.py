"""Development / Demo Seed Script for ProductIQ Storefront.

Populates the 8 canonical Storefront products matching the Google Stitch reference:
1. Nike Air Zoom Pegasus 40 (Running Shoes) - ₹8,999
2. Apple MacBook Air M3 (Laptops) - ₹1,14,900
3. Sony WH-1000XM5 (Headphones) - ₹29,990
4. Adidas Ultraboost Light (Running Shoes) - ₹12,999
5. Samsung Galaxy S24 (Smartphones) - ₹74,999
6. Logitech MX Mechanical (Keyboards) - ₹13,995
7. Dell UltraSharp U2723QE (Monitors) - ₹49,999
8. Bose QuietComfort Ultra (Audio) - ₹26,900

Idempotent: running multiple times updates existing records without duplication.
"""

import os
import sys
import urllib.request

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.models.category import Category
from app.models.product import Product
from app.models.image import Image

DEMO_CATEGORIES = [
    {"name": "Running Shoes", "description": "High-performance running and athletic footwear"},
    {"name": "Laptops", "description": "High-performance and ultra-portable notebooks"},
    {"name": "Headphones", "description": "Noise-cancelling, wireless and audiophile headphones"},
    {"name": "Smartphones", "description": "Flagship and everyday smartphones"},
    {"name": "Keyboards", "description": "Mechanical, wireless and productivity keyboards"},
    {"name": "Monitors", "description": "Ultra-sharp 4K and professional displays"},
    {"name": "Audio", "description": "Premium wireless earbuds, speakers and spatial sound"},
    {"name": "Footwear", "description": "Lifestyle and athletic footwear"},
    {"name": "Electronics", "description": "Modern consumer electronics"},
    {"name": "Computers", "description": "Workstations, laptops and computer accessories"},
    {"name": "Apparel", "description": "Comfortable lifestyle and active clothing"},
    {"name": "Accessories", "description": "Bags, peripherals and daily essentials"},
    {"name": "Home", "description": "Smart home audio and display gear"},
]

DEMO_PRODUCTS = [
    {
        "sku": "NIKE-PEGASUS-40",
        "brand": "Nike",
        "title": "Air Zoom Pegasus 40",
        "category_name": "Running Shoes",
        "price": 8999.0,
        "description": "Engineered for road runners with dual Zoom Air units, breathable engineered mesh upper, and lightweight React foam cushioning.",
        "image_url": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600&auto=format&fit=crop&q=80",
    },
    {
        "sku": "APPLE-MBA-M3",
        "brand": "Apple",
        "title": "MacBook Air M3",
        "category_name": "Laptops",
        "price": 114900.0,
        "description": "Blazingly fast M3 chip with 8-core CPU and 10-core GPU, stunning 13.6-inch Liquid Retina display, MagSafe charging, and 18-hour battery life.",
        "image_url": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=600&auto=format&fit=crop&q=80",
    },
    {
        "sku": "SONY-WH1000XM5",
        "brand": "Sony",
        "title": "WH-1000XM5",
        "category_name": "Headphones",
        "price": 29990.0,
        "description": "Industry-leading wireless active noise cancelling headphones with Integrated Processor V1, 8 microphones, LDAC Hi-Res audio, and 30-hour battery life.",
        "image_url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&auto=format&fit=crop&q=80",
    },
    {
        "sku": "ADIDAS-ULTRABOOST-LT",
        "brand": "Adidas",
        "title": "Ultraboost Light",
        "category_name": "Running Shoes",
        "price": 12999.0,
        "description": "Experience epic energy return with the lightest Ultraboost yet, featuring 30% lighter Light BOOST material and Continental Better Rubber outsole.",
        "image_url": "https://images.unsplash.com/photo-1587563871167-1ee9c731aefb?w=600&auto=format&fit=crop&q=80",
    },
    {
        "sku": "SAMSUNG-S24",
        "brand": "Samsung",
        "title": "Galaxy S24",
        "category_name": "Smartphones",
        "price": 74999.0,
        "description": "AI-powered flagship smartphone featuring Live Translate, Circle to Search with Google, 50MP ProVisual Engine camera, and Dynamic AMOLED 2X 120Hz display.",
        "image_url": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=600&auto=format&fit=crop&q=80",
    },
    {
        "sku": "LOGI-MX-MECH",
        "brand": "Logitech",
        "title": "MX Mechanical",
        "category_name": "Keyboards",
        "price": 13995.0,
        "description": "Full-size wireless mechanical keyboard with Tactile Quiet low-profile mechanical switches, smart backlighting, multi-device Bluetooth, and USB-C fast charging.",
        "image_url": "https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=600&auto=format&fit=crop&q=80",
    },
    {
        "sku": "DELL-U2723QE",
        "brand": "Dell",
        "title": "UltraSharp U2723QE",
        "category_name": "Monitors",
        "price": 49999.0,
        "description": "27-inch 4K UHD professional monitor with revolutionary IPS Black technology, 2000:1 contrast ratio, 98% DCI-P3 wide color gamut, and 90W USB-C hub connectivity.",
        "image_url": "https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?w=600&auto=format&fit=crop&q=80",
    },
    {
        "sku": "BOSE-QC-ULTRA",
        "brand": "Bose",
        "title": "QuietComfort Ultra",
        "category_name": "Audio",
        "price": 26900.0,
        "description": "Breakthrough spatial audio earbuds with world-class noise cancellation, CustomTune personalized sound, Aware Mode, and up to 24 hours of listening time.",
        "image_url": "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=600&auto=format&fit=crop&q=80",
    },
]


def download_image_safe(url: str, dest_path: str) -> bool:
    """Download image to disk if not already present."""
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
        return True
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp, open(dest_path, "wb") as f:
            f.write(resp.read())
        return True
    except Exception as e:
        print(f"Warning: Failed to download {url}: {e}")
        return False


def seed_demo_storefront():
    db: Session = SessionLocal()
    try:
        print("1. Seeding categories...")
        cat_map = {}
        for cdata in DEMO_CATEGORIES:
            cat = db.query(Category).filter_by(name=cdata["name"]).first()
            if not cat:
                cat = Category(name=cdata["name"])
                db.add(cat)
                db.flush()
                print(f"  + Created category: {cat.name} (id={cat.id})")
            else:
                print(f"  = Found category: {cat.name} (id={cat.id})")
            cat_map[cat.name] = cat.id

        print("\n2. Seeding 8 reference products...")
        for pdata in DEMO_PRODUCTS:
            cat_id = cat_map.get(pdata["category_name"])
            if not cat_id:
                print(f"Error: Category {pdata['category_name']} not found for {pdata['title']}")
                continue

            product = db.query(Product).filter_by(sku=pdata["sku"]).first()
            if not product:
                product = Product(
                    sku=pdata["sku"],
                    brand=pdata["brand"],
                    title=pdata["title"],
                    category_id=cat_id,
                    price=pdata["price"],
                    description=pdata["description"],
                    status="ACTIVE",
                )
                db.add(product)
                db.flush()
                print(f"  + Created product: {product.title} (id={product.id}, SKU={product.sku})")
            else:
                product.brand = pdata["brand"]
                product.title = pdata["title"]
                product.category_id = cat_id
                product.price = pdata["price"]
                product.description = pdata["description"]
                product.status = "ACTIVE"
                db.flush()
                print(f"  = Updated product: {product.title} (id={product.id}, SKU={product.sku})")

            # Handle Product Image
            img_dest = os.path.join("uploads", "products", str(product.id), "product.jpg")
            downloaded = download_image_safe(pdata["image_url"], img_dest)

            local_url = f"uploads/products/{product.id}/product.jpg"
            chosen_url = local_url if downloaded else pdata["image_url"]

            existing_img = db.query(Image).filter_by(product_id=product.id).first()
            file_size = os.path.getsize(img_dest) if os.path.exists(img_dest) else 25000

            if not existing_img:
                img = Image(
                    product_id=product.id,
                    image_url=chosen_url,
                    filename="product.jpg",
                    mime_type="image/jpeg",
                    file_size=file_size,
                    width=800,
                    height=800,
                    display_order=1,
                )
                db.add(img)
                print(f"    + Added image for product {product.id}")
            else:
                existing_img.image_url = chosen_url
                existing_img.file_size = file_size
                print(f"    = Updated image for product {product.id}")

        db.commit()
        print("\nSeed completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"Error during seeding: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_storefront()
