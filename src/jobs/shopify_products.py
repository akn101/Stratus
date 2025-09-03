#!/usr/bin/env python3
"""
Shopify Products ETL Job for Stratus ERP Integration Service.

Fetches products and their variants from Shopify Admin API and loads them into the data warehouse.
Performs full refresh of product catalog data.
"""

import logging
import sys

from ..adapters.shopify import ShopifyClient
from ..db.deps import get_session
from ..db.upserts import upsert_shopify_products, upsert_shopify_variants

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def validate_products_data(products: list[dict], variants: list[dict]) -> None:
    """
    Validate the products and variants data before database operations.

    Args:
        products: List of normalized product dictionaries
        variants: List of normalized variant dictionaries

    Raises:
        ValueError: If validation fails
    """
    # Validate products
    for product in products:
        if not product.get("product_id"):
            raise ValueError(f"Product missing product_id: {product}")

        if not product.get("created_at"):
            raise ValueError(f"Product missing created_at: {product}")

        if not product.get("updated_at"):
            raise ValueError(f"Product missing updated_at: {product}")

    # Validate variants
    for variant in variants:
        if not variant.get("variant_id"):
            raise ValueError(f"Variant missing variant_id: {variant}")

        if not variant.get("product_id"):
            raise ValueError(f"Variant missing product_id: {variant}")

        if not variant.get("created_at"):
            raise ValueError(f"Variant missing created_at: {variant}")

        if not variant.get("updated_at"):
            raise ValueError(f"Variant missing updated_at: {variant}")

    # Check for orphaned variants
    product_ids = {product["product_id"] for product in products}
    variant_product_ids = {variant["product_id"] for variant in variants}
    orphaned_variants = variant_product_ids - product_ids

    if orphaned_variants:
        logger.warning(
            f"Found {len(orphaned_variants)} variants without corresponding products: {orphaned_variants}"
        )

    logger.info(
        f"Product data validation passed for {len(products)} products and {len(variants)} variants"
    )


def run_shopify_products_sync(shop: str = None, access_token: str = None) -> dict[str, int]:
    """
    Run the Shopify products synchronization job.

    Returns:
        Dictionary with sync statistics
    """
    logger.info("Starting Shopify products sync job (full refresh)")

    try:
        # Initialize Shopify client (parameters ignored, uses env config)
        client = ShopifyClient()

        # Fetch products and variants from Shopify
        logger.info("Fetching products and variants from Shopify Admin API")
        products, variants = client.get_products()

        if not products:
            logger.info("No products to sync")
            return {
                "products_processed": 0,
                "products_inserted": 0,
                "products_updated": 0,
                "variants_processed": 0,
                "variants_inserted": 0,
                "variants_updated": 0,
            }

        # Validate data
        validate_products_data(products, variants)

        # Filter out orphaned variants to avoid FK violations
        product_ids = {p["product_id"] for p in products}
        filtered_variants = [v for v in variants if v.get("product_id") in product_ids]
        dropped_variants = len(variants) - len(filtered_variants)
        if dropped_variants:
            logger.warning(
                f"Dropping {dropped_variants} variants without matching products before upsert"
            )

        # Upsert data to database
        logger.info(f"Upserting {len(products)} products and {len(filtered_variants)} variants")

        with get_session() as session:
            # Upsert products first (parent records)
            products_inserted, products_updated = upsert_shopify_products(products, session)
            logger.info(f"Products - Inserted: {products_inserted}, Updated: {products_updated}")

            # Upsert variants (child records)
            variants_inserted, variants_updated = upsert_shopify_variants(
                filtered_variants, session
            )
            logger.info(f"Variants - Inserted: {variants_inserted}, Updated: {variants_updated}")

        # Return statistics
        stats = {
            "products_processed": len(products),
            "products_inserted": products_inserted,
            "products_updated": products_updated,
            "variants_processed": len(filtered_variants),
            "variants_inserted": variants_inserted,
            "variants_updated": variants_updated,
        }

        logger.info(f"Shopify products sync completed successfully: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Shopify products sync failed: {e}")
        raise


def main():
    """CLI entry point for the Shopify products sync job."""
    try:
        stats = run_shopify_products_sync()

        # Print summary for CLI usage
        print("Shopify Products Sync Summary:")
        print(f"  Products processed: {stats['products_processed']}")
        print(f"  Products inserted: {stats['products_inserted']}")
        print(f"  Products updated: {stats['products_updated']}")
        print(f"  Variants processed: {stats['variants_processed']}")
        print(f"  Variants inserted: {stats['variants_inserted']}")
        print(f"  Variants updated: {stats['variants_updated']}")

        sys.exit(0)

    except KeyboardInterrupt:
        logger.info("Sync job interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Sync job failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
