"""
ShipBob Order Status ETL Job.

Updates order status and tracking information for Shopify orders fulfilled by ShipBob.
Only updates existing orders in the database with new status/tracking information.
"""

import logging
import os
from datetime import UTC, datetime, timedelta

from ..adapters.shipbob import ShipBobClient
from ..db.deps import get_session
from ..db.upserts_shipbob import update_order_tracking

logger = logging.getLogger(__name__)


def validate_status_updates(status_updates):
    """Validate order status update data."""
    if not status_updates:
        logger.warning("No status updates to validate")
        return

    for update in status_updates:
        if not update.get("order_id"):
            raise ValueError(f"Status update missing order_id: {update}")

        if not update.get("updated_at"):
            raise ValueError(f"Status update missing updated_at: {update}")

        # Ensure tracking is properly formatted
        tracking = update.get("tracking")
        if tracking:
            if not isinstance(tracking, dict):
                logger.warning(
                    f"Invalid tracking format for order {update['order_id']}: {tracking}"
                )
                update["tracking"] = None
            else:
                # Extract individual tracking fields for database storage
                update["tracking_number"] = tracking.get("tracking_number")
                update["carrier"] = tracking.get("carrier")
                update["tracking_url"] = tracking.get("tracking_url")

        # Set tracking_updated_at timestamp
        update["tracking_updated_at"] = update["updated_at"]

        # Remove the nested tracking dict as we've extracted the fields
        if "tracking" in update:
            del update["tracking"]

    logger.info(f"Validated {len(status_updates)} status updates")


def run_shipbob_orders_sync(token: str = None, lookback_hours: int = None) -> dict:
    """
    Run ShipBob order status sync job.

    Updates order status and tracking for orders that have been updated since
    the lookback period. Only updates existing orders in the database.

    Args:
        lookback_hours: Hours to look back for updates (default: from env or 24)

    Returns:
        Dict with sync statistics
    """
    logger.info("Starting ShipBob order status sync")

    try:
        # Determine lookback period
        if lookback_hours is None:
            lookback_hours = int(os.getenv("SHIPBOB_STATUS_LOOKBACK_HOURS", "24"))

        since_dt = datetime.now(UTC) - timedelta(hours=lookback_hours)
        since_iso = since_dt.isoformat().replace("+00:00", "Z")

        logger.info(f"Looking for ShipBob order updates since {since_iso} ({lookback_hours} hours)")

        # Initialize client (reads config from env by default; mocked in tests)
        client = ShipBobClient()

        # Fetch order status updates
        logger.info("Fetching order status updates from ShipBob API")
        status_updates = client.get_order_statuses(since_iso)

        # Validate data
        validate_status_updates(status_updates)

        if not status_updates:
            logger.info("No order status updates found")
            return {
                "orders_processed": 0,
                "orders_updated": 0,
                "orders_with_tracking": 0,
                "errors": 0,
            }

        # Count updates with tracking info
        orders_with_tracking = sum(1 for update in status_updates if update.get("tracking_number"))

        # Update order tracking in database
        logger.info(f"Updating {len(status_updates)} orders with status/tracking info")

        with get_session() as session:
            inserted, updated = update_order_tracking(status_updates, session)
            session.commit()

        stats = {
            "orders_processed": len(status_updates),
            "orders_updated": updated,  # inserted should be 0 for tracking updates
            "orders_with_tracking": orders_with_tracking,
            "errors": 0,
        }

        logger.info(
            f"ShipBob status sync completed successfully: "
            f"processed={stats['orders_processed']}, "
            f"updated={stats['orders_updated']}, "
            f"with_tracking={stats['orders_with_tracking']}"
        )

        return stats

    except Exception as e:
        logger.error(f"ShipBob status sync failed: {e}", exc_info=True)
        return {
            "orders_processed": 0,
            "orders_updated": 0,
            "orders_with_tracking": 0,
            "errors": 1,
        }


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run the sync
    result = run_shipbob_orders_sync()

    # Exit with appropriate code
    if result["errors"] > 0:
        exit(1)
    else:
        logger.info("ShipBob status sync job completed successfully")
        exit(0)
