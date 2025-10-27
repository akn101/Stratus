#!/usr/bin/env python3
"""
FreeAgent Bills ETL Job

Syncs bills (expenses/purchases) from FreeAgent API into the data warehouse.
Supports full sync and incremental sync with graceful handling of unavailable endpoints.

Usage:
    python -m src.jobs.freeagent_bills [--from-date YYYY-MM-DD] [--to-date YYYY-MM-DD] [--full-sync]
"""

import argparse
import logging
from datetime import datetime


from src.adapters.freeagent import FreeAgentFeatureUnavailableError, create_freeagent_client
from src.common.etl import extract_id_from_url, parse_date
from src.db.upserts_source_specific import upsert_freeagent_bills
from src.utils.config import get_secret

logger = logging.getLogger(__name__)


def transform_bill(bill: dict) -> dict:
    """Transform FreeAgent bill to database format."""
    # Extract IDs from URLs
    bill_id = extract_id_from_url(bill.get("url", ""))
    contact_id = extract_id_from_url(bill.get("contact", ""))
    project_id = extract_id_from_url(bill.get("project", ""))

    # Parse dates
    dated_on = parse_date(bill.get("dated_on"))
    due_on = parse_date(bill.get("due_on"))
    created_at_api = parse_date(bill.get("created_at"))
    updated_at_api = parse_date(bill.get("updated_at"))

    # Transform bill data
    transformed = {
        "bill_id": bill_id,
        "source": "freeagent",
        "reference": bill.get("reference"),
        "dated_on": dated_on,
        "due_on": due_on,
        "contact_id": contact_id,
        "contact_name": bill.get("contact_name"),
        "net_value": bill.get("net_value"),
        "sales_tax_value": bill.get("sales_tax_value"),
        "total_value": bill.get("total_value"),
        "paid_value": bill.get("paid_value"),
        "due_value": bill.get("due_value"),
        "status": bill.get("status"),
        "sales_tax_status": bill.get("sales_tax_status"),
        "comments": bill.get("comments"),
        "project_id": project_id if project_id else None,
        "created_at_api": created_at_api,
        "updated_at_api": updated_at_api,
    }

    return transformed


def run_freeagent_bills_etl(
    access_token: str,
    from_date: str | None = None,
    to_date: str | None = None,
    full_sync: bool = False,
) -> dict[str, int]:
    """
    Run FreeAgent bills ETL job.

    Args:
        access_token: FreeAgent OAuth access token
        from_date: Start date for incremental sync (YYYY-MM-DD)
        to_date: End date for incremental sync (YYYY-MM-DD)
        full_sync: Whether to perform full sync (ignores date filters)

    Returns:
        Dict with sync statistics (inserted, updated, total)
    """
    logger.info("Starting FreeAgent bills ETL job")

    # Initialize FreeAgent client
    client = create_freeagent_client(access_token=access_token)

    # Use default date range if none specified and not full sync
    if not full_sync and not from_date and not to_date:
        from_date, to_date = client.get_default_date_range()
        logger.info(f"Using default date range: {from_date} to {to_date}")

    # Clear date filters for full sync
    if full_sync:
        from_date = None
        to_date = None
        logger.info("Performing full sync (ignoring date filters)")

    try:
        # Extract bills from FreeAgent API
        logger.info("Fetching bills from FreeAgent API")
        bills = client.get_bills(from_date=from_date, to_date=to_date)

        if not bills:
            logger.info("No bills found")
            return {"inserted": 0, "updated": 0, "total": 0}

        logger.info(f"Retrieved {len(bills)} bills from FreeAgent")

        # Transform bills
        transformed_bills = []
        for bill in bills:
            try:
                transformed = transform_bill(bill)
                if transformed["bill_id"]:  # Only include bills with valid IDs
                    transformed_bills.append(transformed)
                else:
                    logger.warning(f"Skipping bill with invalid ID: {bill}")
            except Exception as e:
                logger.error(f"Error transforming bill {bill}: {e}")
                continue

        if not transformed_bills:
            logger.warning("No valid bills to upsert after transformation")
            return {"inserted": 0, "updated": 0, "total": 0}

        logger.info(f"Transformed {len(transformed_bills)} valid bills")

        # Load into database
        inserted, updated = upsert_freeagent_bills(transformed_bills)
        total = len(transformed_bills)

        logger.info(
            f"FreeAgent bills ETL completed: {inserted} inserted, {updated} updated, {total} total"
        )

        return {"inserted": inserted, "updated": updated, "total": total}

    except FreeAgentFeatureUnavailableError as e:
        logger.warning(f"Bills feature unavailable: {e}")
        return {"inserted": 0, "updated": 0, "total": 0, "error": "feature_unavailable"}

    except Exception as e:
        logger.error(f"Error in FreeAgent bills ETL: {e}")
        raise


def main():
    """CLI entry point for FreeAgent bills ETL job."""
    parser = argparse.ArgumentParser(description="FreeAgent Bills ETL Job")
    parser.add_argument("--from-date", help="Start date for sync (YYYY-MM-DD)")
    parser.add_argument("--to-date", help="End date for sync (YYYY-MM-DD)")
    parser.add_argument("--full-sync", action="store_true", help="Perform full sync")
    parser.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Get access token from environment/secrets
    access_token = get_secret("FREEAGENT_ACCESS_TOKEN")
    if not access_token:
        logger.error("FREEAGENT_ACCESS_TOKEN not found in environment")
        return 1

    try:
        result = run_freeagent_bills_etl(
            access_token=access_token,
            from_date=args.from_date,
            to_date=args.to_date,
            full_sync=args.full_sync,
        )

        print(f"Bills ETL Result: {result}")
        return 0

    except Exception as e:
        logger.error(f"Failed to run FreeAgent bills ETL: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
