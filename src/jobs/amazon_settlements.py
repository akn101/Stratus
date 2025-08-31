#!/usr/bin/env python3
"""
Amazon Settlements ETL Job for Stratus ERP Integration Service.

Fetches settlement reports from Amazon SP-API and loads them into the data warehouse.
Handles report generation, polling, downloading, and parsing of settlement data.
"""

import logging
import os
import sys
from datetime import UTC, datetime, timedelta

from ..adapters.amazon import AmazonConfig
from ..adapters.amazon_finance import AmazonFinanceClient
from ..db.deps import get_session
from ..db.upserts import upsert_settlement_lines, upsert_settlements

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_settlement_date_range() -> tuple[str, str]:
    """
    Calculate the date range for settlement report based on AMZ_SETTLEMENT_LOOKBACK_DAYS.

    Returns:
        Tuple of (start_iso, end_iso) timestamp strings
    """
    lookback_days = int(os.getenv("AMZ_SETTLEMENT_LOOKBACK_DAYS", "14"))

    # End date is yesterday (settlements are typically finalized with a delay)
    end_date = datetime.now(UTC) - timedelta(days=1)

    # Start date is lookback_days before the end date
    start_date = end_date - timedelta(days=lookback_days)

    # Format as ISO strings
    start_iso = (
        start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    end_iso = (
        end_date.replace(hour=23, minute=59, second=59, microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    logger.info(f"Settlement date range: {start_iso} to {end_iso} (lookback: {lookback_days} days)")
    return start_iso, end_iso


def validate_settlement_data(settlement_header: dict, settlement_lines: list[dict]) -> None:
    """
    Validate settlement data before database operations.

    Args:
        settlement_header: Settlement header dictionary
        settlement_lines: List of settlement line dictionaries

    Raises:
        ValueError: If validation fails
    """
    # Validate settlement header
    if not settlement_header.get("settlement_id"):
        raise ValueError(f"Settlement missing settlement_id: {settlement_header}")

    if not settlement_header.get("currency"):
        raise ValueError(f"Settlement missing currency: {settlement_header}")

    # Validate settlement lines
    settlement_id = settlement_header["settlement_id"]
    for line in settlement_lines:
        if not line.get("settlement_id"):
            raise ValueError(f"Settlement line missing settlement_id: {line}")

        if line["settlement_id"] != settlement_id:
            raise ValueError(f"Settlement line has mismatched settlement_id: {line}")

        if line.get("amount") is None:
            raise ValueError(f"Settlement line missing amount: {line}")

    logger.info(
        f"Settlement data validation passed: {settlement_id} with {len(settlement_lines)} lines"
    )


def process_single_settlement_report(
    client: AmazonFinanceClient, start_iso: str, end_iso: str
) -> dict[str, int]:
    """
    Process a single settlement report: request, poll, download, parse, and store.

    Args:
        client: Amazon finance client
        start_iso: Start date for the report
        end_iso: End date for the report

    Returns:
        Dictionary with processing statistics
    """
    logger.info(f"Processing settlement report for {start_iso} to {end_iso}")

    try:
        # Step 1: Request the report
        report_id = client.request_settlement_report(start_iso, end_iso)
        logger.info(f"Settlement report requested: {report_id}")

        # Step 2: Poll for completion (with retries built into the client)
        logger.info(f"Polling for report completion: {report_id}")
        download_url = client.poll_report(report_id)
        logger.info(f"Report completed, download URL obtained: {report_id}")

        # Step 3: Download and parse the settlement data
        logger.info(f"Downloading and parsing settlement data: {report_id}")
        settlement_header, settlement_lines = client.download_and_parse_settlement(download_url)

        if not settlement_header.get("settlement_id"):
            logger.warning(f"No settlement data found in report {report_id}")
            return {
                "reports_processed": 1,
                "settlements_processed": 0,
                "settlements_inserted": 0,
                "settlements_updated": 0,
                "lines_processed": 0,
                "lines_inserted": 0,
                "lines_updated": 0,
            }

        # Step 4: Validate the data
        validate_settlement_data(settlement_header, settlement_lines)

        # Step 5: Upsert to database
        logger.info(
            f"Upserting settlement {settlement_header['settlement_id']} with {len(settlement_lines)} lines"
        )

        with get_session() as session:
            # Upsert settlement header
            settlements_inserted, settlements_updated = upsert_settlements(
                [settlement_header], session
            )
            logger.info(
                f"Settlement header - Inserted: {settlements_inserted}, Updated: {settlements_updated}"
            )

            # Upsert settlement lines
            lines_inserted, lines_updated = upsert_settlement_lines(settlement_lines, session)
            logger.info(f"Settlement lines - Inserted: {lines_inserted}, Updated: {lines_updated}")

        return {
            "reports_processed": 1,
            "settlements_processed": 1,
            "settlements_inserted": settlements_inserted,
            "settlements_updated": settlements_updated,
            "lines_processed": len(settlement_lines),
            "lines_inserted": lines_inserted,
            "lines_updated": lines_updated,
        }

    except Exception as e:
        logger.error(f"Error processing settlement report: {e}")
        raise


def run_amazon_settlements_sync() -> dict[str, int]:
    """
    Run the Amazon settlements synchronization job.

    Returns:
        Dictionary with sync statistics
    """
    logger.info("Starting Amazon settlements sync job")

    try:
        # Initialize Amazon finance client
        config = AmazonConfig.from_env()
        client = AmazonFinanceClient(config)

        # Calculate date range
        start_iso, end_iso = get_settlement_date_range()

        # Process settlement report
        logger.info("Processing Amazon settlement reports")
        stats = process_single_settlement_report(client, start_iso, end_iso)

        logger.info(f"Amazon settlements sync completed successfully: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Amazon settlements sync failed: {e}")
        raise


def main():
    """CLI entry point for the Amazon settlements sync job."""
    try:
        stats = run_amazon_settlements_sync()

        # Print summary for CLI usage
        print("Amazon Settlements Sync Summary:")
        print(f"  Reports processed: {stats['reports_processed']}")
        print(f"  Settlements processed: {stats['settlements_processed']}")
        print(f"  Settlements inserted: {stats['settlements_inserted']}")
        print(f"  Settlements updated: {stats['settlements_updated']}")
        print(f"  Lines processed: {stats['lines_processed']}")
        print(f"  Lines inserted: {stats['lines_inserted']}")
        print(f"  Lines updated: {stats['lines_updated']}")

        sys.exit(0)

    except KeyboardInterrupt:
        logger.info("Sync job interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Sync job failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
