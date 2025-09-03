#!/usr/bin/env python3
"""
FreeAgent Bank Accounts ETL Job

Syncs bank accounts from FreeAgent API into the data warehouse.
Bank accounts are typically synced once and rarely change.

Usage:
    python -m src.jobs.freeagent_bank_accounts [--log-level INFO]
"""

import argparse
import logging
from datetime import datetime
from urllib.parse import urlparse

from src.adapters.freeagent import FreeAgentFeatureUnavailableError, create_freeagent_client
from src.db.upserts_source_specific import upsert_freeagent_bank_accounts
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


def transform_bank_account(bank_account: dict) -> dict:
    """Transform FreeAgent bank account to database format."""
    # Extract IDs from URLs
    bank_account_id = extract_id_from_url(bank_account.get("url", ""))
    default_bill_category_id = extract_id_from_url(bank_account.get("default_bill_category", ""))

    # Parse dates
    opening_balance_date = parse_date(bank_account.get("opening_balance_date"))

    # Transform bank account data
    transformed = {
        "bank_account_id": bank_account_id,
        "source": "freeagent",
        "name": bank_account.get("name"),
        "bank_name": bank_account.get("bank_name"),
        "type": bank_account.get("type"),
        "account_number": bank_account.get("account_number"),
        "sort_code": bank_account.get("sort_code"),
        "iban": bank_account.get("iban"),
        "bic": bank_account.get("bic"),
        "current_balance": bank_account.get("current_balance"),
        "currency": bank_account.get("currency"),
        "is_primary": str(bank_account.get("is_primary"))
        if bank_account.get("is_primary") is not None
        else None,
        "is_personal": str(bank_account.get("is_personal"))
        if bank_account.get("is_personal") is not None
        else None,
        "email_new_transactions": str(bank_account.get("email_new_transactions"))
        if bank_account.get("email_new_transactions") is not None
        else None,
        "default_bill_category_id": default_bill_category_id if default_bill_category_id else None,
        "opening_balance_date": opening_balance_date,
    }

    return transformed


def run_freeagent_bank_accounts_etl(access_token: str) -> dict[str, int]:
    """
    Run FreeAgent bank accounts ETL job.

    Args:
        access_token: FreeAgent OAuth access token

    Returns:
        Dict with sync statistics (inserted, updated, total)
    """
    logger.info("Starting FreeAgent bank accounts ETL job")

    # Initialize FreeAgent client
    client = create_freeagent_client(access_token=access_token)

    try:
        # Extract bank accounts from FreeAgent API
        logger.info("Fetching bank accounts from FreeAgent API")
        bank_accounts = client.get_bank_accounts()

        if not bank_accounts:
            logger.info("No bank accounts found")
            return {"inserted": 0, "updated": 0, "total": 0}

        logger.info(f"Retrieved {len(bank_accounts)} bank accounts from FreeAgent")

        # Transform bank accounts
        transformed_bank_accounts = []
        for bank_account in bank_accounts:
            try:
                transformed = transform_bank_account(bank_account)
                if transformed["bank_account_id"]:  # Only include bank accounts with valid IDs
                    transformed_bank_accounts.append(transformed)
                else:
                    logger.warning(f"Skipping bank account with invalid ID: {bank_account}")
            except Exception as e:
                logger.error(f"Error transforming bank account {bank_account}: {e}")
                continue

        if not transformed_bank_accounts:
            logger.warning("No valid bank accounts to upsert after transformation")
            return {"inserted": 0, "updated": 0, "total": 0}

        logger.info(f"Transformed {len(transformed_bank_accounts)} valid bank accounts")

        # Load into database
        inserted, updated = upsert_freeagent_bank_accounts(transformed_bank_accounts)
        total = len(transformed_bank_accounts)

        logger.info(
            f"FreeAgent bank accounts ETL completed: {inserted} inserted, {updated} updated, {total} total"
        )

        return {"inserted": inserted, "updated": updated, "total": total}

    except FreeAgentFeatureUnavailableError as e:
        logger.warning(f"Bank accounts feature unavailable: {e}")
        return {"inserted": 0, "updated": 0, "total": 0, "error": "feature_unavailable"}

    except Exception as e:
        logger.error(f"Error in FreeAgent bank accounts ETL: {e}")
        raise


def main():
    """CLI entry point for FreeAgent bank accounts ETL job."""
    parser = argparse.ArgumentParser(description="FreeAgent Bank Accounts ETL Job")
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
        result = run_freeagent_bank_accounts_etl(access_token=access_token)

        print(f"Bank Accounts ETL Result: {result}")
        return 0

    except Exception as e:
        logger.error(f"Failed to run FreeAgent bank accounts ETL: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
