#!/usr/bin/env python3
"""
Amazon FBA Inventory ETL Job for Stratus ERP Integration Service.

Performs a full refresh of FBA inventory data from Amazon SP-API.
Fetches all inventory summaries across all fulfillment centers and updates the warehouse.
"""

import logging
import sys

from ..adapters.amazon_inventory import AmazonInventoryClient
from ..db.deps import get_session
from ..db.upserts import upsert_inventory

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def validate_inventory_data(inventory_items: list[dict]) -> None:
    """
    Validate inventory data before database operations.

    Args:
        inventory_items: List of normalized inventory dictionaries

    Raises:
        ValueError: If validation fails
    """
    for item in inventory_items:
        if not item.get("sku"):
            raise ValueError(f"Inventory item missing SKU: {item}")

        # Validate quantities are non-negative integers
        for qty_field in ["on_hand", "reserved", "inbound"]:
            qty_value = item.get(qty_field)
            if qty_value is not None and (not isinstance(qty_value, int) or qty_value < 0):
                raise ValueError(f"Inventory item has invalid {qty_field}: {item}")

        if not item.get("updated_at"):
            raise ValueError(f"Inventory item missing updated_at timestamp: {item}")

    logger.info(f"Inventory data validation passed for {len(inventory_items)} items")


def run_amazon_inventory_sync() -> dict[str, int]:
    """
    Run the Amazon FBA inventory synchronization job.

    Performs a full refresh of all inventory data.

    Returns:
        Dictionary with sync statistics
    """
    logger.info("Starting Amazon FBA inventory sync job (full refresh)")

    try:
        # Initialize Amazon inventory client
        client = AmazonInventoryClient()

        # Fetch all inventory summaries
        logger.info("Fetching all FBA inventory summaries from Amazon SP-API")
        inventory_items = client.get_all_inventory_summaries()

        if not inventory_items:
            logger.info("No inventory items to sync")
            return {"items_processed": 0, "items_inserted": 0, "items_updated": 0}

        # Validate data
        validate_inventory_data(inventory_items)

        # Group items by SKU to handle multiple fulfillment centers
        # Note: This implementation takes the most recent record per SKU
        # In practice, you might want to aggregate quantities across FCs
        sku_inventory = {}
        for item in inventory_items:
            sku = item["sku"]
            if sku not in sku_inventory:
                sku_inventory[sku] = item
            else:
                # Aggregate quantities if multiple FCs for same SKU
                existing = sku_inventory[sku]
                existing["on_hand"] += item["on_hand"]
                existing["reserved"] += item["reserved"]
                existing["inbound"] += item["inbound"]

                # Keep the latest FC info (could be improved with FC priority logic)
                if item.get("fc"):
                    existing["fc"] = item["fc"]

        # Convert back to list
        aggregated_items = list(sku_inventory.values())

        logger.info(
            f"Aggregated {len(inventory_items)} items into {len(aggregated_items)} unique SKUs"
        )

        # Upsert to database
        logger.info(f"Upserting {len(aggregated_items)} inventory items")

        with get_session() as session:
            items_inserted, items_updated = upsert_inventory(aggregated_items, session)
            logger.info(f"Inventory - Inserted: {items_inserted}, Updated: {items_updated}")

        # Return statistics
        stats = {
            "items_processed": len(aggregated_items),
            "items_inserted": items_inserted,
            "items_updated": items_updated,
        }

        logger.info(f"Amazon FBA inventory sync completed successfully: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Amazon FBA inventory sync failed: {e}")
        raise


def run_amazon_inventory_incremental_sync(skus: list[str] = None) -> dict[str, int]:
    """
    Run an incremental Amazon FBA inventory sync for specific SKUs.

    Args:
        skus: Optional list of SKUs to sync. If None, syncs all.

    Returns:
        Dictionary with sync statistics

    Note: This is a placeholder for future incremental sync functionality.
    The current Amazon FBA Inventory API doesn't support filtering by SKU,
    so this performs the same full refresh but filters results.
    """
    logger.info("Starting Amazon FBA inventory incremental sync")

    if not skus:
        logger.info("No SKUs specified, falling back to full sync")
        return run_amazon_inventory_sync()

    logger.info(f"Requested sync for {len(skus)} specific SKUs: {skus[:5]}...")

    try:
        # Initialize client
        client = AmazonInventoryClient()

        # Fetch all inventory (API limitation - no SKU filtering)
        all_inventory = client.get_all_inventory_summaries()

        # Filter to requested SKUs
        sku_set = set(skus)
        filtered_inventory = [item for item in all_inventory if item.get("sku") in sku_set]

        logger.info(f"Found {len(filtered_inventory)} items matching requested SKUs")

        if not filtered_inventory:
            return {"items_processed": 0, "items_inserted": 0, "items_updated": 0}

        # Validate and upsert
        validate_inventory_data(filtered_inventory)

        with get_session() as session:
            items_inserted, items_updated = upsert_inventory(filtered_inventory, session)
            logger.info(f"Inventory - Inserted: {items_inserted}, Updated: {items_updated}")

        stats = {
            "items_processed": len(filtered_inventory),
            "items_inserted": items_inserted,
            "items_updated": items_updated,
        }

        logger.info(f"Amazon FBA inventory incremental sync completed: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Amazon FBA inventory incremental sync failed: {e}")
        raise


def main():
    """CLI entry point for the Amazon FBA inventory sync job."""
    try:
        # Check for incremental mode (future enhancement)
        if len(sys.argv) > 1 and sys.argv[1] == "--incremental":
            # Parse SKUs from remaining arguments
            skus = sys.argv[2:] if len(sys.argv) > 2 else None
            stats = run_amazon_inventory_incremental_sync(skus)
        else:
            # Default to full refresh
            stats = run_amazon_inventory_sync()

        # Print summary for CLI usage
        print("Amazon FBA Inventory Sync Summary:")
        print(f"  Items processed: {stats['items_processed']}")
        print(f"  Items inserted: {stats['items_inserted']}")
        print(f"  Items updated: {stats['items_updated']}")

        sys.exit(0)

    except KeyboardInterrupt:
        logger.info("Sync job interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Sync job failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
