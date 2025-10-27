#!/usr/bin/env python3
"""
Amazon Orders ETL Job for Stratus ERP Integration Service.

Fetches orders from Amazon SP-API and loads them into the data warehouse.
Supports incremental sync with configurable lookback period.
"""

import logging
import os
import sys
from datetime import UTC, datetime, timedelta

from ..adapters.amazon import AmazonOrdersClient
from ..db.deps import get_session
from ..db.upserts import upsert_order_items, upsert_orders

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_sync_since_timestamp() -> str:
    """
    Calculate the timestamp to sync from based on AMZ_SYNC_LOOKBACK_HOURS.

    Returns:
        ISO 8601 timestamp string in UTC
    """
    lookback_hours = int(os.getenv("AMZ_SYNC_LOOKBACK_HOURS", "24"))
    since_dt = datetime.now(UTC) - timedelta(hours=lookback_hours)
    since_iso = since_dt.isoformat().replace("+00:00", "Z")

    logger.info(f"Syncing orders since {since_iso} (lookback: {lookback_hours} hours)")
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
    # Validate orders
    for order in orders:
        if not order.get("order_id"):
            raise ValueError(f"Order missing order_id: {order}")
        if not order.get("source"):
            raise ValueError(f"Order missing source: {order}")
        if not order.get("purchase_date"):
            raise ValueError(f"Order missing purchase_date: {order}")

    # Validate order items
    for item in order_items:
        if not item.get("order_id"):
            raise ValueError(f"Order item missing order_id: {item}")
        if not item.get("sku"):
            raise ValueError(f"Order item missing sku: {item}")
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


def run_amazon_orders_etl() -> dict[str, int]:
    """
    Run the Amazon orders synchronization job.

    Returns:
        Dictionary with sync statistics
    """
    logger.info("Starting Amazon orders sync job")

    try:
        # Initialize Amazon client (config loaded internally; avoids test env coupling)
        client = AmazonOrdersClient()

        # Calculate sync timestamp
        since_iso = get_sync_since_timestamp()

        # Fetch orders from Amazon
        logger.info("Fetching orders from Amazon SP-API")
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
            # Upsert orders
            orders_inserted, orders_updated = upsert_orders(orders, session)
            logger.info(f"Orders - Inserted: {orders_inserted}, Updated: {orders_updated}")

            # Upsert order items
            items_inserted, items_updated = upsert_order_items(filtered_items, session)
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

        logger.info(f"Amazon orders sync completed successfully: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Amazon orders sync failed: {e}")
        raise


def main():
    """CLI entry point for the Amazon orders sync job."""
    try:
        stats = run_amazon_orders_etl()

        # Print summary for CLI usage
        print("Amazon Orders Sync Summary:")
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
