"""
ShipBob Inventory ETL Job.

Fetches current inventory levels from ShipBob API and stores them in the data warehouse.
Performs full refresh of ShipBob inventory data.
"""

import logging

from ..adapters.shipbob import ShipBobClient, ShipBobConfig
from ..db.deps import get_session
from ..db.upserts_source_specific import upsert_shipbob_inventory

logger = logging.getLogger(__name__)


def validate_inventory_data(inventory_records):
    """Validate inventory data before database insertion."""
    if not inventory_records:
        logger.warning("No inventory records to validate")
        return

    for record in inventory_records:
        if not record.get("sku"):
            raise ValueError(f"Inventory record missing SKU: {record}")

        # Ensure numeric fields are integers
        numeric_fields = [
            "quantity_on_hand",
            "quantity_available",
            "quantity_reserved",
            "quantity_incoming",
            "fulfillable_quantity",
            "backordered_quantity",
            "exception_quantity",
            "internal_transfer_quantity",
        ]

        for field in numeric_fields:
            if record.get(field) is not None:
                try:
                    # Allow strings like "95.0" by coercing via float first
                    val = record[field]
                    if isinstance(val, str):
                        record[field] = int(float(val))
                    else:
                        record[field] = int(val)
                except (ValueError, TypeError):
                    logger.warning(
                        f"Invalid {field} value for SKU {record.get('sku')}: {record.get(field)}"
                    )
                    record[field] = 0

    logger.info(f"Validated {len(inventory_records)} inventory records")


def run_shipbob_inventory_etl() -> dict:
    """
    Run ShipBob inventory sync job.

    Performs a full refresh of inventory data from ShipBob.

    Returns:
        Dict with sync statistics
    """
    logger.info("Starting ShipBob inventory sync")

    try:
        # Initialize ShipBob client (loads config from environment)
        config = ShipBobConfig.from_env()
        client = ShipBobClient(config=config)

        # Fetch inventory data
        logger.info("Fetching inventory from ShipBob API")
        inventory_records = client.get_inventory()

        # Drop empty/invalid SKUs early
        inventory_records = [r for r in inventory_records if r.get("sku")]

        # Validate data
        validate_inventory_data(inventory_records)

        if not inventory_records:
            logger.info("No inventory records found")
            return {
                "inventory_processed": 0,
                "inventory_inserted": 0,
                "inventory_updated": 0,
                "errors": 0,
            }

        # Upsert to database
        logger.info(f"Upserting {len(inventory_records)} inventory records to database")

        with get_session() as session:
            inserted, updated = upsert_shipbob_inventory(inventory_records, session)
            session.commit()

        stats = {
            "inventory_processed": len(inventory_records),
            "inventory_inserted": inserted,
            "inventory_updated": updated,
            "errors": 0,
        }

        logger.info(
            f"ShipBob inventory sync completed successfully: "
            f"processed={stats['inventory_processed']}, "
            f"inserted={stats['inventory_inserted']}, "
            f"updated={stats['inventory_updated']}"
        )

        return stats

    except Exception as e:
        logger.error(f"ShipBob inventory sync failed: {e}", exc_info=True)
        return {
            "inventory_processed": 0,
            "inventory_inserted": 0,
            "inventory_updated": 0,
            "errors": 1,
        }


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run the sync
    result = run_shipbob_inventory_etl()

    # Exit with appropriate code
    if result["errors"] > 0:
        exit(1)
    else:
        logger.info("ShipBob inventory sync job completed successfully")
        exit(0)
