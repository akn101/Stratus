"""
ShipBob Products ETL Job.

Fetches products and variants from ShipBob API for product catalog management.
Includes product attributes, dimensions, weight, value, and variant information.
"""

import json
import logging

from ..adapters.shipbob import ShipBobClient
from ..db.deps import get_session
from ..db.upserts_shipbob import upsert_shipbob_products, upsert_shipbob_variants

logger = logging.getLogger(__name__)


def validate_products_data(products, variants):
    """Validate products and variants data before database insertion."""
    if not products and not variants:
        logger.warning("No products or variants to validate")
        return

    # Validate products
    for product in products:
        if not product.get("product_id"):
            raise ValueError(f"Product missing product_id: {product}")

        # Serialize JSON fields
        for json_field in ["dimensions", "weight", "value"]:
            if isinstance(product.get(json_field), dict):
                product[json_field] = json.dumps(product[json_field])

        # Convert boolean fields to strings for database storage
        for bool_field in [
            "is_case",
            "is_lot",
            "is_active",
            "is_bundle",
            "is_digital",
            "is_hazmat",
        ]:
            if isinstance(product.get(bool_field), bool):
                product[bool_field] = str(product[bool_field]).lower()

    # Validate variants
    product_ids = {p["product_id"] for p in products}
    for variant in variants:
        if not variant.get("variant_id"):
            raise ValueError(f"Variant missing variant_id: {variant}")

        if not variant.get("product_id"):
            raise ValueError(f"Variant missing product_id: {variant}")

        # Check for orphaned variants
        if variant["product_id"] not in product_ids:
            logger.warning(
                f"Variant {variant['variant_id']} has orphaned product_id {variant['product_id']}"
            )

        # Serialize JSON fields
        for json_field in ["dimensions", "weight", "value"]:
            if isinstance(variant.get(json_field), dict):
                variant[json_field] = json.dumps(variant[json_field])

        # Convert boolean fields to strings
        if isinstance(variant.get("is_active"), bool):
            variant["is_active"] = str(variant["is_active"]).lower()

    # Filter out orphaned variants
    valid_variants = [v for v in variants if v["product_id"] in product_ids]
    orphaned_count = len(variants) - len(valid_variants)
    if orphaned_count > 0:
        logger.warning(f"Filtered out {orphaned_count} orphaned variants")
        variants.clear()
        variants.extend(valid_variants)

    logger.info(f"Validated {len(products)} products and {len(variants)} variants")


def run_shipbob_products_sync() -> dict:
    """
    Run ShipBob products sync job.

    Performs full refresh of product catalog data from ShipBob.

    Returns:
        Dict with sync statistics
    """
    logger.info("Starting ShipBob products sync")

    try:
        # Initialize client
        client = ShipBobClient()

        # Fetch products and variants
        logger.info("Fetching products and variants from ShipBob API")
        products, variants = client.get_products()

        # Validate data
        validate_products_data(products, variants)

        if not products and not variants:
            logger.info("No products or variants found")
            return {
                "products_processed": 0,
                "products_inserted": 0,
                "products_updated": 0,
                "variants_processed": 0,
                "variants_inserted": 0,
                "variants_updated": 0,
                "errors": 0,
            }

        # Upsert to database
        logger.info(f"Upserting {len(products)} products and {len(variants)} variants")

        with get_session() as session:
            # First upsert products
            products_inserted, products_updated = 0, 0
            if products:
                products_inserted, products_updated = upsert_shipbob_products(products, session)

            # Then upsert variants (depends on products)
            variants_inserted, variants_updated = 0, 0
            if variants:
                variants_inserted, variants_updated = upsert_shipbob_variants(variants, session)

            session.commit()

        stats = {
            "products_processed": len(products),
            "products_inserted": products_inserted,
            "products_updated": products_updated,
            "variants_processed": len(variants),
            "variants_inserted": variants_inserted,
            "variants_updated": variants_updated,
            "errors": 0,
        }

        logger.info(
            f"ShipBob products sync completed successfully: "
            f"products_processed={stats['products_processed']}, "
            f"products_inserted={stats['products_inserted']}, "
            f"products_updated={stats['products_updated']}, "
            f"variants_processed={stats['variants_processed']}, "
            f"variants_inserted={stats['variants_inserted']}, "
            f"variants_updated={stats['variants_updated']}"
        )

        return stats

    except Exception as e:
        logger.error(f"ShipBob products sync failed: {e}", exc_info=True)
        return {
            "products_processed": 0,
            "products_inserted": 0,
            "products_updated": 0,
            "variants_processed": 0,
            "variants_inserted": 0,
            "variants_updated": 0,
            "errors": 1,
        }


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run the sync
    result = run_shipbob_products_sync()

    # Exit with appropriate code
    if result["errors"] > 0:
        exit(1)
    else:
        logger.info("ShipBob products sync job completed successfully")
        exit(0)
