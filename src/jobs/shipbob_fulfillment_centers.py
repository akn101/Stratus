"""
ShipBob Fulfillment Centers ETL Job.

Fetches fulfillment center information from ShipBob API for geographic and operational analytics.
Includes location details, contact information, and timezone data.
"""

import logging

from ..adapters.shipbob import ShipBobClient
from ..db.deps import get_session
from ..db.upserts_shipbob import upsert_shipbob_fulfillment_centers

logger = logging.getLogger(__name__)


def validate_fulfillment_centers_data(centers_records):
    """Validate fulfillment centers data before database insertion."""
    if not centers_records:
        logger.warning("No fulfillment centers to validate")
        return

    for record in centers_records:
        if not record.get("center_id"):
            raise ValueError(f"Fulfillment center missing center_id: {record}")

    logger.info(f"Validated {len(centers_records)} fulfillment centers")


def run_shipbob_fulfillment_centers_etl() -> dict:
    """
    Run ShipBob fulfillment centers sync job.

    Fetches fulfillment center information for geographic and operational analytics.
    This is typically a small, stable dataset that doesn't change frequently.

    Returns:
        Dict with sync statistics
    """
    logger.info("Starting ShipBob fulfillment centers sync")

    try:
        # Initialize client
        client = ShipBobClient()

        # Fetch fulfillment centers
        logger.info("Fetching fulfillment centers from ShipBob API")
        centers_records = client.get_fulfillment_centers()

        # Validate data
        validate_fulfillment_centers_data(centers_records)

        if not centers_records:
            logger.info("No fulfillment centers found")
            return {
                "centers_processed": 0,
                "centers_inserted": 0,
                "centers_updated": 0,
                "errors": 0,
            }

        # Upsert to database
        logger.info(f"Upserting {len(centers_records)} fulfillment center records")

        with get_session() as session:
            inserted, updated = upsert_shipbob_fulfillment_centers(centers_records, session)
            session.commit()

        stats = {
            "centers_processed": len(centers_records),
            "centers_inserted": inserted,
            "centers_updated": updated,
            "errors": 0,
        }

        # Log center locations for visibility
        center_locations = [
            f"{c.get('name', 'Unknown')} ({c.get('city', '')}, {c.get('state', '')})"
            for c in centers_records
        ]

        logger.info(
            f"ShipBob fulfillment centers sync completed successfully: "
            f"processed={stats['centers_processed']}, "
            f"inserted={stats['centers_inserted']}, "
            f"updated={stats['centers_updated']}"
        )

        logger.info(f"Active fulfillment centers: {', '.join(center_locations)}")

        return stats

    except Exception as e:
        logger.error(f"ShipBob fulfillment centers sync failed: {e}", exc_info=True)
        return {
            "centers_processed": 0,
            "centers_inserted": 0,
            "centers_updated": 0,
            "errors": 1,
        }


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run the sync
    result = run_shipbob_fulfillment_centers_etl()

    # Exit with appropriate code
    if result["errors"] > 0:
        exit(1)
    else:
        logger.info("ShipBob fulfillment centers sync job completed successfully")
        exit(0)
