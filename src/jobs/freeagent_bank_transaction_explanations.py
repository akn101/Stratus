#!/usr/bin/env python3
"""
FreeAgent Bank Transaction Explanations ETL Job

Syncs bank transaction explanations from FreeAgent API into the data warehouse.
Explanations categorize bank transactions for accounting purposes.
Supports full sync and incremental sync with graceful handling of unavailable endpoints.

Usage:
    python -m src.jobs.freeagent_bank_transaction_explanations [--from-date YYYY-MM-DD] [--to-date YYYY-MM-DD] [--full-sync]
"""

import argparse
import logging
from datetime import datetime
from urllib.parse import urlparse

from src.adapters.freeagent import FreeAgentFeatureUnavailableError, create_freeagent_client
from src.db.upserts import upsert_freeagent_bank_transaction_explanations
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


def transform_bank_transaction_explanation(explanation: dict) -> dict:
    """Transform FreeAgent bank transaction explanation to database format."""
    # Extract IDs from URLs
    explanation_id = extract_id_from_url(explanation.get("url", ""))
    bank_transaction_id = extract_id_from_url(explanation.get("bank_transaction", ""))
    bank_account_id = extract_id_from_url(explanation.get("bank_account", ""))
    category_id = extract_id_from_url(explanation.get("category", ""))
    invoice_id = extract_id_from_url(explanation.get("invoice", ""))
    bill_id = extract_id_from_url(explanation.get("bill", ""))

    # Parse dates
    dated_on = parse_date(explanation.get("dated_on"))
    created_at_api = parse_date(explanation.get("created_at"))
    updated_at_api = parse_date(explanation.get("updated_at"))

    # Transform explanation data
    transformed = {
        "explanation_id": explanation_id,
        "source": "freeagent",
        "bank_transaction_id": bank_transaction_id,
        "bank_account_id": bank_account_id,
        "dated_on": dated_on,
        "amount": explanation.get("amount"),
        "description": explanation.get("description"),
        "category_id": category_id if category_id else None,
        "category_name": explanation.get("category_name"),
        "foreign_currency_amount": explanation.get("foreign_currency_amount"),
        "foreign_currency_type": explanation.get("foreign_currency_type"),
        "gross_value": explanation.get("gross_value"),
        "sales_tax_rate": explanation.get("sales_tax_rate"),
        "sales_tax_value": explanation.get("sales_tax_value"),
        "invoice_id": invoice_id if invoice_id else None,
        "bill_id": bill_id if bill_id else None,
        "created_at_api": created_at_api,
        "updated_at_api": updated_at_api,
    }

    return transformed


def run_freeagent_bank_transaction_explanations_etl(
    access_token: str,
    from_date: str | None = None,
    to_date: str | None = None,
    full_sync: bool = False,
) -> dict[str, int]:
    """
    Run FreeAgent bank transaction explanations ETL job.

    Args:
        access_token: FreeAgent OAuth access token
        from_date: Start date for incremental sync (YYYY-MM-DD)
        to_date: End date for incremental sync (YYYY-MM-DD)
        full_sync: Whether to perform full sync (ignores date filters)

    Returns:
        Dict with sync statistics (inserted, updated, total)
    """
    logger.info("Starting FreeAgent bank transaction explanations ETL job")

    # Initialize FreeAgent client
    client = create_freeagent_client(access_token)

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
        # Extract bank transaction explanations from FreeAgent API
        logger.info("Fetching bank transaction explanations from FreeAgent API")
        explanations = client.get_bank_transaction_explanations(
            from_date=from_date, to_date=to_date
        )

        if not explanations:
            logger.info("No bank transaction explanations found")
            return {"inserted": 0, "updated": 0, "total": 0}

        logger.info(f"Retrieved {len(explanations)} bank transaction explanations from FreeAgent")

        # Transform explanations
        transformed_explanations = []
        for explanation in explanations:
            try:
                transformed = transform_bank_transaction_explanation(explanation)
                if transformed["explanation_id"]:  # Only include explanations with valid IDs
                    transformed_explanations.append(transformed)
                else:
                    logger.warning(f"Skipping explanation with invalid ID: {explanation}")
            except Exception as e:
                logger.error(f"Error transforming bank transaction explanation {explanation}: {e}")
                continue

        if not transformed_explanations:
            logger.warning("No valid bank transaction explanations to upsert after transformation")
            return {"inserted": 0, "updated": 0, "total": 0}

        logger.info(
            f"Transformed {len(transformed_explanations)} valid bank transaction explanations"
        )

        # Load into database
        inserted, updated = upsert_freeagent_bank_transaction_explanations(transformed_explanations)
        total = len(transformed_explanations)

        logger.info(
            f"FreeAgent bank transaction explanations ETL completed: {inserted} inserted, {updated} updated, {total} total"
        )

        return {"inserted": inserted, "updated": updated, "total": total}

    except FreeAgentFeatureUnavailableError as e:
        logger.warning(f"Bank transaction explanations feature unavailable: {e}")
        return {"inserted": 0, "updated": 0, "total": 0, "error": "feature_unavailable"}

    except Exception as e:
        logger.error(f"Error in FreeAgent bank transaction explanations ETL: {e}")
        raise


def main():
    """CLI entry point for FreeAgent bank transaction explanations ETL job."""
    parser = argparse.ArgumentParser(description="FreeAgent Bank Transaction Explanations ETL Job")
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
        result = run_freeagent_bank_transaction_explanations_etl(
            access_token=access_token,
            from_date=args.from_date,
            to_date=args.to_date,
            full_sync=args.full_sync,
        )

        print(f"Bank Transaction Explanations ETL Result: {result}")
        return 0

    except Exception as e:
        logger.error(f"Failed to run FreeAgent bank transaction explanations ETL: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
