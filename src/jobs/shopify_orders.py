#!/usr/bin/env python3
"""
Shopify Orders ETL Job for Stratus ERP Integration Service.

Fetches orders from Shopify Admin API and loads them into the data warehouse.
Supports incremental sync with configurable lookback period.
"""

import logging
import os
import sys
from datetime import UTC, datetime, timedelta

from ..adapters.shopify import ShopifyClient, ShopifyConfig
from ..db.deps import get_session
from ..db.upserts_source_specific import upsert_shopify_orders, upsert_shopify_order_items

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_sync_since_timestamp() -> str:
    """
    Calculate the timestamp to sync from based on SHOPIFY_SYNC_LOOKBACK_HOURS.

    Returns:
        ISO 8601 timestamp string in UTC
    """
    lookback_hours = int(os.getenv("SHOPIFY_SYNC_LOOKBACK_HOURS", "24"))
    since_dt = datetime.now(UTC) - timedelta(hours=lookback_hours)
    since_iso = since_dt.isoformat().replace("+00:00", "Z")

    logger.info(f"Syncing Shopify orders since {since_iso} (lookback: {lookback_hours} hours)")
    return since_iso


def validate_orders_data(orders: list[dict], order_items: list[dict]) -> None:
    """
    Validate the orders and order items data before database operations.

    Args:
        orders: List of normalized order dictionaries
        order_items: List of normalized order item dictionaries

    Raises:
        ValueError: If validation fails
    """
    # Validate orders (source-specific, so no need to check source field)
    for order in orders:
        if not order.get("order_id"):
            raise ValueError(f"Order missing order_id: {order}")
        if not order.get("purchase_date"):
            raise ValueError(f"Order missing purchase_date: {order}")

    # Validate order items
    for item in order_items:
        if not item.get("order_id"):
            raise ValueError(f"Order item missing order_id: {item}")
        if not item.get("sku"):
            logger.warning(f"Order item missing sku (Shopify allows this): {item}")
        if item.get("qty") is None or item.get("qty") < 0:
            raise ValueError(f"Order item has invalid qty: {item}")

    # Check for orphaned items
    order_ids = {order["order_id"] for order in orders}
    item_order_ids = {item["order_id"] for item in order_items}
    orphaned_items = item_order_ids - order_ids

    if orphaned_items:
        logger.warning(
            f"Found {len(orphaned_items)} order items without corresponding orders: {orphaned_items}"
        )


def run_shopify_orders_etl(
    shop: str,
    access_token: str,
    api_version: str = "2024-07",
    lookback_hours: int = 24,
    **kwargs
) -> dict[str, int]:
    """
    Run the Shopify orders synchronization job.

    Args:
        shop: Shopify shop name
        access_token: Shopify API access token
        api_version: Shopify API version
        lookback_hours: Hours to look back for incremental sync
        **kwargs: Additional configuration parameters

    Returns:
        Dictionary with sync statistics
    """
    logger.info("Starting Shopify orders sync job")

    try:
        # Initialize Shopify client with provided credentials
        config = ShopifyConfig(shop=shop, access_token=access_token, api_version=api_version)
        client = ShopifyClient(config=config)

        # Calculate sync timestamp using provided lookback hours
        since_dt = datetime.now(UTC) - timedelta(hours=lookback_hours)
        since_iso = since_dt.isoformat().replace("+00:00", "Z")
        logger.info(f"Syncing Shopify orders since {since_iso} (lookback: {lookback_hours} hours)")

        # Fetch orders from Shopify
        logger.info("Fetching orders from Shopify Admin API")
        orders, order_items = client.get_orders_since(since_iso)

        if not orders:
            logger.info("No orders to sync")
            return {
                "orders_processed": 0,
                "orders_inserted": 0,
                "orders_updated": 0,
                "items_processed": 0,
                "items_inserted": 0,
                "items_updated": 0,
            }

        # Validate data
        validate_orders_data(orders, order_items)

        # Filter out orphaned items to avoid FK violations
        order_ids = {o["order_id"] for o in orders}
        filtered_items = [it for it in order_items if it.get("order_id") in order_ids]
        dropped = len(order_items) - len(filtered_items)
        if dropped:
            logger.warning(f"Dropping {dropped} order items without matching orders before upsert")

        # Upsert data to database
        logger.info(f"Upserting {len(orders)} orders and {len(filtered_items)} order items")

        with get_session() as session:
            # Upsert orders to Shopify-specific table
            orders_inserted, orders_updated = upsert_shopify_orders(orders, session)
            logger.info(f"Orders - Inserted: {orders_inserted}, Updated: {orders_updated}")

            # Upsert order items to Shopify-specific table
            items_inserted, items_updated = upsert_shopify_order_items(filtered_items, session)
            logger.info(f"Order items - Inserted: {items_inserted}, Updated: {items_updated}")

        # Return statistics
        stats = {
            "orders_processed": len(orders),
            "orders_inserted": orders_inserted,
            "orders_updated": orders_updated,
            "items_processed": len(filtered_items),
            "items_inserted": items_inserted,
            "items_updated": items_updated,
        }

        logger.info(f"Shopify orders sync completed successfully: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Shopify orders sync failed: {e}")
        raise


def main():
    """CLI entry point for the Shopify orders sync job."""
    try:
        # Load configuration from environment
        config = ShopifyConfig.from_env()
        stats = run_shopify_orders_etl(
            shop=config.shop,
            access_token=config.access_token,
            api_version=config.api_version,
            lookback_hours=int(os.getenv("SHOPIFY_SYNC_LOOKBACK_HOURS", "24"))
        )

        # Print summary for CLI usage
        print("Shopify Orders Sync Summary:")
        print(f"  Orders processed: {stats['orders_processed']}")
        print(f"  Orders inserted: {stats['orders_inserted']}")
        print(f"  Orders updated: {stats['orders_updated']}")
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
