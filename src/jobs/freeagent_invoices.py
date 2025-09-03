#!/usr/bin/env python3
"""
FreeAgent Invoices ETL Job

Syncs invoices (sales) from FreeAgent API into the data warehouse.
Supports full sync and incremental sync with graceful handling of unavailable endpoints.

Usage:
    python -m src.jobs.freeagent_invoices [--from-date YYYY-MM-DD] [--to-date YYYY-MM-DD] [--full-sync]
"""

import argparse
import logging
from datetime import datetime
from urllib.parse import urlparse

from src.adapters.freeagent import FreeAgentFeatureUnavailableError, create_freeagent_client
from src.db.upserts_source_specific import upsert_freeagent_invoices
from src.utils.config import get_secret

logger = logging.getLogger(__name__)


def extract_id_from_url(url: str) -> str:
    """Extract numeric ID from FreeAgent API URL."""
    if not url:
        return ""
    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").split("/")
    return path_parts[-1] if path_parts else ""


def parse_date(date_str: str) -> datetime | None:
    """Parse FreeAgent date string to datetime."""
    if not date_str:
        return None

    try:
        # Handle different date formats
        if "T" in date_str:
            # ISO datetime format
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        else:
            # Date-only format
            return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def transform_invoice(invoice: dict) -> dict:
    """Transform FreeAgent invoice to database format."""
    # Extract IDs from URLs
    invoice_id = extract_id_from_url(invoice.get("url", ""))
    contact_id = extract_id_from_url(invoice.get("contact", ""))
    project_id = extract_id_from_url(invoice.get("project", ""))

    # Parse dates
    dated_on = parse_date(invoice.get("dated_on"))
    due_on = parse_date(invoice.get("due_on"))
    created_at_api = parse_date(invoice.get("created_at"))
    updated_at_api = parse_date(invoice.get("updated_at"))

    # Transform invoice data
    transformed = {
        "invoice_id": invoice_id,
        "source": "freeagent",
        "reference": invoice.get("reference"),
        "dated_on": dated_on,
        "due_on": due_on,
        "contact_id": contact_id,
        "contact_name": invoice.get("contact_name"),
        "net_value": invoice.get("net_value"),
        "sales_tax_value": invoice.get("sales_tax_value"),
        "total_value": invoice.get("total_value"),
        "paid_value": invoice.get("paid_value"),
        "due_value": invoice.get("due_value"),
        "currency": invoice.get("currency"),
        "exchange_rate": invoice.get("exchange_rate"),
        "net_value_in_base_currency": invoice.get("net_value_in_base_currency"),
        "status": invoice.get("status"),
        "payment_terms_in_days": invoice.get("payment_terms_in_days"),
        "sales_tax_status": invoice.get("sales_tax_status"),
        "outside_of_sales_tax_scope": str(invoice.get("outside_of_sales_tax_scope"))
        if invoice.get("outside_of_sales_tax_scope") is not None
        else None,
        "initial_sales_tax_rate": invoice.get("initial_sales_tax_rate"),
        "comments": invoice.get("comments"),
        "project_id": project_id if project_id else None,
        "created_at_api": created_at_api,
        "updated_at_api": updated_at_api,
    }

    return transformed


def run_freeagent_invoices_etl(
    access_token: str,
    from_date: str | None = None,
    to_date: str | None = None,
    full_sync: bool = False,
    lookback_days: int = 60,
    **kwargs
) -> dict[str, int]:
    """
    Run FreeAgent invoices ETL job.

    Args:
        access_token: FreeAgent OAuth access token
        from_date: Start date for incremental sync (YYYY-MM-DD)
        to_date: End date for incremental sync (YYYY-MM-DD)
        full_sync: Whether to perform full sync (ignores date filters)

    Returns:
        Dict with sync statistics (inserted, updated, total)
    """
    logger.info("Starting FreeAgent invoices ETL job")

    # Initialize FreeAgent client
    client = create_freeagent_client(access_token=access_token)

    # Use lookback_days or default date range if none specified and not full sync
    if not full_sync and not from_date and not to_date:
        if lookback_days:
            from datetime import datetime, timedelta
            to_date_dt = datetime.now()
            from_date_dt = to_date_dt - timedelta(days=lookback_days)
            from_date = from_date_dt.strftime('%Y-%m-%d')
            to_date = to_date_dt.strftime('%Y-%m-%d')
            logger.info(f"Using lookback period: {from_date} to {to_date} ({lookback_days} days)")
        else:
            from_date, to_date = client.get_default_date_range()
            logger.info(f"Using default date range: {from_date} to {to_date}")

    # Clear date filters for full sync
    if full_sync:
        from_date = None
        to_date = None
        logger.info("Performing full sync (ignoring date filters)")

    try:
        # Extract invoices from FreeAgent API
        logger.info("Fetching invoices from FreeAgent API")
        invoices = client.get_invoices(from_date=from_date, to_date=to_date)

        if not invoices:
            logger.info("No invoices found")
            return {"inserted": 0, "updated": 0, "total": 0}

        logger.info(f"Retrieved {len(invoices)} invoices from FreeAgent")

        # Transform invoices
        transformed_invoices = []
        for invoice in invoices:
            try:
                transformed = transform_invoice(invoice)
                if transformed["invoice_id"]:  # Only include invoices with valid IDs
                    transformed_invoices.append(transformed)
                else:
                    logger.warning(f"Skipping invoice with invalid ID: {invoice}")
            except Exception as e:
                logger.error(f"Error transforming invoice {invoice}: {e}")
                continue

        if not transformed_invoices:
            logger.warning("No valid invoices to upsert after transformation")
            return {"inserted": 0, "updated": 0, "total": 0}

        logger.info(f"Transformed {len(transformed_invoices)} valid invoices")

        # Load into database
        inserted, updated = upsert_freeagent_invoices(transformed_invoices)
        total = len(transformed_invoices)

        logger.info(
            f"FreeAgent invoices ETL completed: {inserted} inserted, {updated} updated, {total} total"
        )

        return {"inserted": inserted, "updated": updated, "total": total}

    except FreeAgentFeatureUnavailableError as e:
        logger.warning(f"Invoices feature unavailable: {e}")
        return {"inserted": 0, "updated": 0, "total": 0, "error": "feature_unavailable"}

    except Exception as e:
        logger.error(f"Error in FreeAgent invoices ETL: {e}")
        raise


def main():
    """CLI entry point for FreeAgent invoices ETL job."""
    parser = argparse.ArgumentParser(description="FreeAgent Invoices ETL Job")
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
        result = run_freeagent_invoices_etl(
            access_token=access_token,
            from_date=args.from_date,
            to_date=args.to_date,
            full_sync=args.full_sync,
        )

        print(f"Invoices ETL Result: {result}")
        return 0

    except Exception as e:
        logger.error(f"Failed to run FreeAgent invoices ETL: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
