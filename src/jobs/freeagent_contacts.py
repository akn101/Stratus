#!/usr/bin/env python3
"""
FreeAgent Contacts ETL Job

Syncs contacts (customers and suppliers) from FreeAgent API into the data warehouse.
Supports full sync and incremental sync with graceful handling of unavailable endpoints.

Usage:
    python -m src.jobs.freeagent_contacts [--from-date YYYY-MM-DD] [--to-date YYYY-MM-DD] [--full-sync]
"""

import argparse
import logging
from datetime import datetime
from urllib.parse import urlparse

from src.adapters.freeagent import FreeAgentFeatureUnavailableError, create_freeagent_client
from src.db.upserts_source_specific import upsert_freeagent_contacts
from src.utils.config import get_secret

logger = logging.getLogger(__name__)


def extract_id_from_url(url: str) -> str:
    """Extract numeric ID from FreeAgent API URL."""
    if not url:
        return ""
    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").split("/")
    return path_parts[-1] if path_parts else ""


def transform_contact(contact: dict) -> dict:
    """Transform FreeAgent contact to database format."""
    # Extract IDs from URLs
    contact_id = extract_id_from_url(contact.get("url", ""))

    # Parse dates
    created_at_api = None
    updated_at_api = None
    if contact.get("created_at"):
        try:
            created_at_api = datetime.fromisoformat(contact["created_at"].replace("Z", "+00:00"))
        except ValueError:
            logger.warning(
                f"Invalid created_at date for contact {contact_id}: {contact.get('created_at')}"
            )

    if contact.get("updated_at"):
        try:
            updated_at_api = datetime.fromisoformat(contact["updated_at"].replace("Z", "+00:00"))
        except ValueError:
            logger.warning(
                f"Invalid updated_at date for contact {contact_id}: {contact.get('updated_at')}"
            )

    # Transform contact data
    transformed = {
        "contact_id": contact_id,
        "source": "freeagent",
        "organisation_name": contact.get("organisation_name"),
        "first_name": contact.get("first_name"),
        "last_name": contact.get("last_name"),
        "contact_name_on_invoices": contact.get("contact_name_on_invoices"),
        "email": contact.get("email"),
        "phone_number": contact.get("phone_number"),
        "mobile": contact.get("mobile"),
        "fax": contact.get("fax"),
        "address1": contact.get("address1"),
        "address2": contact.get("address2"),
        "address3": contact.get("address3"),
        "town": contact.get("town"),
        "region": contact.get("region"),
        "postcode": contact.get("postcode"),
        "country": contact.get("country"),
        "contact_type": contact.get("contact_type"),
        "default_payment_terms_in_days": contact.get("default_payment_terms_in_days"),
        "charge_sales_tax": contact.get("charge_sales_tax"),
        "sales_tax_registration_number": contact.get("sales_tax_registration_number"),
        "active_projects_count": contact.get("active_projects_count"),
        "account_balance": contact.get("account_balance"),
        "uses_contact_invoice_sequence": contact.get("uses_contact_invoice_sequence"),
        "status": contact.get("status"),
        "created_at_api": created_at_api,
        "updated_at_api": updated_at_api,
    }

    return transformed


def run_freeagent_contacts_etl(
    access_token: str,
    from_date: str | None = None,
    to_date: str | None = None,
    full_sync: bool = False,
) -> dict[str, int]:
    """
    Run FreeAgent contacts ETL job.

    Args:
        access_token: FreeAgent OAuth access token
        from_date: Start date for incremental sync (YYYY-MM-DD)
        to_date: End date for incremental sync (YYYY-MM-DD)
        full_sync: Whether to perform full sync (ignores date filters)

    Returns:
        Dict with sync statistics (inserted, updated, total)
    """
    logger.info("Starting FreeAgent contacts ETL job")

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
        # Extract contacts from FreeAgent API
        logger.info("Fetching contacts from FreeAgent API")
        contacts = client.get_contacts(from_date=from_date, to_date=to_date)

        if not contacts:
            logger.info("No contacts found")
            return {"inserted": 0, "updated": 0, "total": 0}

        logger.info(f"Retrieved {len(contacts)} contacts from FreeAgent")

        # Transform contacts
        transformed_contacts = []
        for contact in contacts:
            try:
                transformed = transform_contact(contact)
                if transformed["contact_id"]:  # Only include contacts with valid IDs
                    transformed_contacts.append(transformed)
                else:
                    logger.warning(f"Skipping contact with invalid ID: {contact}")
            except Exception as e:
                logger.error(f"Error transforming contact {contact}: {e}")
                continue

        if not transformed_contacts:
            logger.warning("No valid contacts to upsert after transformation")
            return {"inserted": 0, "updated": 0, "total": 0}

        logger.info(f"Transformed {len(transformed_contacts)} valid contacts")

        # Load into database
        inserted, updated = upsert_freeagent_contacts(transformed_contacts)
        total = len(transformed_contacts)

        logger.info(
            f"FreeAgent contacts ETL completed: {inserted} inserted, {updated} updated, {total} total"
        )

        return {"inserted": inserted, "updated": updated, "total": total}

    except FreeAgentFeatureUnavailableError as e:
        logger.warning(f"Contacts feature unavailable: {e}")
        return {"inserted": 0, "updated": 0, "total": 0, "error": "feature_unavailable"}

    except Exception as e:
        logger.error(f"Error in FreeAgent contacts ETL: {e}")
        raise


def main():
    """CLI entry point for FreeAgent contacts ETL job."""
    parser = argparse.ArgumentParser(description="FreeAgent Contacts ETL Job")
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
        result = run_freeagent_contacts_etl(
            access_token=access_token,
            from_date=args.from_date,
            to_date=args.to_date,
            full_sync=args.full_sync,
        )

        print(f"Contacts ETL Result: {result}")
        return 0

    except Exception as e:
        logger.error(f"Failed to run FreeAgent contacts ETL: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
