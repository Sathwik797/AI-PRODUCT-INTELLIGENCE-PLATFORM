"""Backfill Embeddings CLI.

Phase 06: Implements Q52, Q53.
Explicit management command to backfill embeddings across existing catalog products.
Leverages EmbeddingService directly without duplicating embedding or hashing logic.
Safe to retry and skips unchanged products.

Usage:
    python -m app.commands.backfill_embeddings [--force] [--limit N] [--product-id ID]
"""

import argparse
import logging
import sys

from app.db.database import SessionLocal
from app.models.product import Product
from app.repositories.product_repository import ProductRepository
from app.services.embedding_service import EmbeddingService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("backfill_embeddings")


def run_backfill(
    force: bool = False,
    limit: int = 100000,
    product_id: int | None = None,
    service: EmbeddingService | None = None
) -> dict[str, int]:
    """Executes backfill of product embeddings using EmbeddingService."""
    db = SessionLocal()
    embedding_service = service or EmbeddingService()
    product_repo = ProductRepository()

    try:
        if product_id is not None:
            prod = product_repo.get_by_id(db, product_id)
            products = [prod] if prod else []
        else:
            products = product_repo.get_all(db)
            if limit:
                products = products[:limit]

        total = len(products)
        logger.info(f"Starting embedding backfill for {total} product(s)... (force={force})")

        generated = 0
        skipped = 0
        failed = 0

        for idx, product in enumerate(products, 1):
            pid = product.id
            try:
                text, current_hash = embedding_service.build_embedding_document(db, product)
                existing_emb = embedding_service.embedding_repository.get_by_product_id(db, pid)

                # Skip unchanged if not forced (Q53)
                if (
                    not force
                    and existing_emb is not None
                    and existing_emb.status == "READY"
                    and existing_emb.content_hash == current_hash
                    and embedding_service.vector_store.contains(existing_emb.vector_id)
                ):
                    logger.info(f"[{idx}/{total}] Product ID {pid}: Content hash matches & vector present. Skipping.")
                    skipped += 1
                    continue

                logger.info(f"[{idx}/{total}] Product ID {pid}: Generating embedding...")
                embedding_service.generate_product_embedding(db, pid)
                generated += 1

            except Exception as e:
                logger.error(f"[{idx}/{total}] Product ID {pid}: Generation failed: {e}")
                failed += 1

        summary = {
            "total": total,
            "generated": generated,
            "skipped": skipped,
            "failed": failed
        }

        print("\n" + "=" * 50)
        print("EMBEDDING BACKFILL SUMMARY")
        print("=" * 50)
        print(f"Total Evaluated: {total}")
        print(f"Generated/Updated: {generated}")
        print(f"Skipped (Unchanged): {skipped}")
        print(f"Failed: {failed}")
        print(f"Vector Store Count: {embedding_service.vector_store.count()}")
        print("=" * 50 + "\n")

        return summary

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill vector embeddings for catalog products.")
    parser.add_argument("--force", action="store_true", help="Force regenerate even if content hash matches.")
    parser.add_argument("--limit", type=int, default=100000, help="Maximum number of products to process.")
    parser.add_argument("--product-id", type=int, default=None, help="Process a single specific product ID.")

    args = parser.parse_args()
    summary = run_backfill(
        force=args.force,
        limit=args.limit,
        product_id=args.product_id
    )

    if summary["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
