"""
ShipBob Returns ETL Job.

Fetches return orders from ShipBob API for cost analysis and return rate analytics.
Includes return items, processing costs, and fulfillment center information.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

from ..adapters.shipbob import ShipBobClient
from ..db.deps import get_session
from ..db.upserts_shipbob import upsert_shipbob_returns

logger = logging.getLogger(__name__)


def validate_returns_data(returns_records):
    """Validate returns data before database insertion."""
    if not returns_records:
        logger.warning("No returns records to validate")
        return

    for record in returns_records:
        if not record.get("return_id"):
            raise ValueError(f"Return record missing return_id: {record}")

        # Serialize JSON fields
        if isinstance(record.get("items"), list):
            record["items"] = json.dumps(record["items"])

        if isinstance(record.get("transactions"), list):
            record["transactions"] = json.dumps(record["transactions"])

    logger.info(f"Validated {len(returns_records)} returns records")


def run_shipbob_returns_sync(lookback_days: int = None) -> dict:
    """
    Run ShipBob returns sync job.

    Fetches return orders from ShipBob for cost analysis and return rate tracking.

    Args:
        lookback_days: Days to look back for returns (default: from env or 30)

    Returns:
        Dict with sync statistics
    """
    logger.info("Starting ShipBob returns sync")

    try:
        # Determine lookback period
        if lookback_days is None:
            import os

            lookback_days = int(os.getenv("SHIPBOB_RETURNS_LOOKBACK_DAYS", "30"))

        since_dt = datetime.now(UTC) - timedelta(days=lookback_days)
        since_iso = since_dt.isoformat().replace("+00:00", "Z")

        logger.info(f"Looking for ShipBob returns since {since_iso} ({lookback_days} days)")

        # Initialize client
        client = ShipBobClient()

        # Fetch returns data
        logger.info("Fetching returns from ShipBob API")
        returns_records = client.get_returns(since_iso)

        # Validate data
        validate_returns_data(returns_records)

        if not returns_records:
            logger.info("No returns records found")
            return {
                "returns_processed": 0,
                "returns_inserted": 0,
                "returns_updated": 0,
                "errors": 0,
            }

        # Calculate total cost for reporting
        total_cost = sum(
            float(r.get("total_cost", 0)) for r in returns_records if r.get("total_cost")
        )

        # Upsert to database
        logger.info(f"Upserting {len(returns_records)} returns records to database")

        with get_session() as session:
            inserted, updated = upsert_shipbob_returns(returns_records, session)
            session.commit()

        stats = {
            "returns_processed": len(returns_records),
            "returns_inserted": inserted,
            "returns_updated": updated,
            "total_return_cost": total_cost,
            "errors": 0,
        }

        logger.info(
            f"ShipBob returns sync completed successfully: "
            f"processed={stats['returns_processed']}, "
            f"inserted={stats['returns_inserted']}, "
            f"updated={stats['returns_updated']}, "
            f"total_cost=${stats['total_return_cost']:.2f}"
        )

        return stats

    except Exception as e:
        logger.error(f"ShipBob returns sync failed: {e}", exc_info=True)
        return {
            "returns_processed": 0,
            "returns_inserted": 0,
            "returns_updated": 0,
            "total_return_cost": 0,
            "errors": 1,
        }


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run the sync
    result = run_shipbob_returns_sync()

    # Exit with appropriate code
    if result["errors"] > 0:
        exit(1)
    else:
        logger.info("ShipBob returns sync job completed successfully")
        exit(0)
