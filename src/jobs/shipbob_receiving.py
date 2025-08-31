"""
ShipBob Receiving Orders ETL Job.

Fetches warehouse receiving orders (WROs) from ShipBob API for inbound logistics tracking.
Includes expected vs received quantities, purchase orders, and fulfillment center data.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

from ..adapters.shipbob import ShipBobClient
from ..db.deps import get_session
from ..db.upserts_shipbob import upsert_shipbob_receiving_orders

logger = logging.getLogger(__name__)


def validate_receiving_data(receiving_records):
    """Validate receiving order data before database insertion."""
    if not receiving_records:
        logger.warning("No receiving records to validate")
        return

    for record in receiving_records:
        if not record.get("wro_id"):
            raise ValueError(f"Receiving record missing wro_id: {record}")

        # Serialize JSON fields
        if isinstance(record.get("inventory_quantities"), list):
            record["inventory_quantities"] = json.dumps(record["inventory_quantities"])

        if isinstance(record.get("status_history"), list):
            record["status_history"] = json.dumps(record["status_history"])

    logger.info(f"Validated {len(receiving_records)} receiving records")


def run_shipbob_receiving_sync(lookback_days: int = None) -> dict:
    """
    Run ShipBob receiving orders sync job.

    Fetches warehouse receiving orders for inbound logistics tracking.

    Args:
        lookback_days: Days to look back for receiving orders (default: from env or 14)

    Returns:
        Dict with sync statistics
    """
    logger.info("Starting ShipBob receiving orders sync")

    try:
        # Determine lookback period
        if lookback_days is None:
            import os

            lookback_days = int(os.getenv("SHIPBOB_RECEIVING_LOOKBACK_DAYS", "14"))

        since_dt = datetime.now(UTC) - timedelta(days=lookback_days)
        since_iso = since_dt.isoformat().replace("+00:00", "Z")

        logger.info(
            f"Looking for ShipBob receiving orders since {since_iso} ({lookback_days} days)"
        )

        # Initialize client
        client = ShipBobClient()

        # Fetch receiving orders
        logger.info("Fetching receiving orders from ShipBob API")
        receiving_records = client.get_receiving_orders(since_iso)

        # Validate data
        validate_receiving_data(receiving_records)

        if not receiving_records:
            logger.info("No receiving orders found")
            return {
                "receiving_orders_processed": 0,
                "receiving_orders_inserted": 0,
                "receiving_orders_updated": 0,
                "purchase_orders_count": 0,
                "errors": 0,
            }

        # Count unique purchase orders
        unique_pos = {
            r.get("purchase_order_number")
            for r in receiving_records
            if r.get("purchase_order_number")
        }

        # Upsert to database
        logger.info(f"Upserting {len(receiving_records)} receiving order records to database")

        with get_session() as session:
            inserted, updated = upsert_shipbob_receiving_orders(receiving_records, session)
            session.commit()

        stats = {
            "receiving_orders_processed": len(receiving_records),
            "receiving_orders_inserted": inserted,
            "receiving_orders_updated": updated,
            "purchase_orders_count": len(unique_pos),
            "errors": 0,
        }

        logger.info(
            f"ShipBob receiving sync completed successfully: "
            f"processed={stats['receiving_orders_processed']}, "
            f"inserted={stats['receiving_orders_inserted']}, "
            f"updated={stats['receiving_orders_updated']}, "
            f"unique_pos={stats['purchase_orders_count']}"
        )

        return stats

    except Exception as e:
        logger.error(f"ShipBob receiving sync failed: {e}", exc_info=True)
        return {
            "receiving_orders_processed": 0,
            "receiving_orders_inserted": 0,
            "receiving_orders_updated": 0,
            "purchase_orders_count": 0,
            "errors": 1,
        }


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run the sync
    result = run_shipbob_receiving_sync()

    # Exit with appropriate code
    if result["errors"] > 0:
        exit(1)
    else:
        logger.info("ShipBob receiving sync job completed successfully")
        exit(0)
