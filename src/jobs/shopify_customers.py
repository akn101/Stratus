#!/usr/bin/env python3
"""
Shopify Customers ETL Job for Stratus ERP Integration Service.

Fetches customers from Shopify Admin API and loads them into the data warehouse.
Supports incremental sync with configurable lookback period.
"""

import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta

from ..adapters.shopify import ShopifyClient
from ..db.deps import get_session
from ..db.upserts import upsert_shopify_customers

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

    logger.info(f"Syncing Shopify customers since {since_iso} (lookback: {lookback_hours} hours)")
    return since_iso


def validate_customers_data(customers: list[dict]) -> None:
    """
    Validate the customers data before database operations.

    Args:
        customers: List of normalized customer dictionaries

    Raises:
        ValueError: If validation fails
    """
    for customer in customers:
        if not customer.get("customer_id"):
            raise ValueError(f"Customer missing customer_id: {customer}")

        if not customer.get("created_at"):
            raise ValueError(f"Customer missing created_at: {customer}")

        if not customer.get("updated_at"):
            raise ValueError(f"Customer missing updated_at: {customer}")

        # Validate orders_count is non-negative
        orders_count = customer.get("orders_count", 0)
        if orders_count < 0:
            raise ValueError(f"Customer has invalid orders_count: {customer}")

    logger.info(f"Customer data validation passed for {len(customers)} customers")


def normalize_customer_tags(customer: dict) -> dict:
    """
    Convert tags list to JSON string for database storage.

    Args:
        customer: Customer dictionary with tags list

    Returns:
        Customer dictionary with tags as JSON string
    """
    normalized = customer.copy()
    tags = customer.get("tags", [])

    if isinstance(tags, list):
        # Convert to JSON string for database storage
        normalized["tags"] = json.dumps(tags) if tags else None
    elif isinstance(tags, str):
        # Already a string, keep as is
        normalized["tags"] = tags if tags else None
    else:
        normalized["tags"] = None

    return normalized


def run_shopify_customers_sync(shop: str = None, access_token: str = None) -> dict[str, int]:
    """
    Run the Shopify customers synchronization job.

    Returns:
        Dictionary with sync statistics
    """
    logger.info("Starting Shopify customers sync job")

    try:
        # Initialize Shopify client (parameters ignored, uses env config)
        client = ShopifyClient()

        # Calculate sync timestamp
        since_iso = get_sync_since_timestamp()

        # Fetch customers from Shopify
        logger.info("Fetching customers from Shopify Admin API")
        customers = client.get_customers_since(since_iso)

        if not customers:
            logger.info("No customers to sync")
            return {"customers_processed": 0, "customers_inserted": 0, "customers_updated": 0}

        # Validate data
        validate_customers_data(customers)

        # Normalize tags for database storage
        normalized_customers = []
        for customer in customers:
            normalized_customer = normalize_customer_tags(customer)
            normalized_customers.append(normalized_customer)

        # Upsert data to database
        logger.info(f"Upserting {len(normalized_customers)} customers")

        with get_session() as session:
            customers_inserted, customers_updated = upsert_shopify_customers(
                normalized_customers, session
            )
            logger.info(f"Customers - Inserted: {customers_inserted}, Updated: {customers_updated}")

        # Return statistics
        stats = {
            "customers_processed": len(normalized_customers),
            "customers_inserted": customers_inserted,
            "customers_updated": customers_updated,
        }

        logger.info(f"Shopify customers sync completed successfully: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Shopify customers sync failed: {e}")
        raise


def main():
    """CLI entry point for the Shopify customers sync job."""
    try:
        stats = run_shopify_customers_sync()

        # Print summary for CLI usage
        print("Shopify Customers Sync Summary:")
        print(f"  Customers processed: {stats['customers_processed']}")
        print(f"  Customers inserted: {stats['customers_inserted']}")
        print(f"  Customers updated: {stats['customers_updated']}")

        sys.exit(0)

    except KeyboardInterrupt:
        logger.info("Sync job interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Sync job failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
