#!/usr/bin/env python3
"""
FreeAgent Categories ETL Job

Syncs accounting categories from FreeAgent API into the data warehouse.
Categories are typically synced once and rarely change.

Usage:
    python -m src.jobs.freeagent_categories [--full-sync]
"""

import argparse
import logging


from src.adapters.freeagent import FreeAgentFeatureUnavailableError, create_freeagent_client
from src.common.etl import extract_id_from_url, parse_date
from src.db.upserts_source_specific import upsert_freeagent_categories
from src.utils.config import get_secret

logger = logging.getLogger(__name__)


def transform_category(category: dict) -> dict:
    """Transform FreeAgent category to database format."""
    # Extract IDs from URLs
    category_id = extract_id_from_url(category.get("url", ""))
    parent_category_id = extract_id_from_url(category.get("parent_category", ""))

    # Transform category data
    transformed = {
        "category_id": category_id,
        "source": "freeagent",
        "description": category.get("description"),
        "nominal_code": category.get("nominal_code"),
        "category_type": category.get("category_type"),
        "parent_category_id": parent_category_id if parent_category_id else None,
        "auto_sales_tax_rate": category.get("auto_sales_tax_rate"),
        "allowable_for_tax": str(category.get("allowable_for_tax"))
        if category.get("allowable_for_tax") is not None
        else None,
        "is_visible": str(category.get("is_visible"))
        if category.get("is_visible") is not None
        else None,
        "group_description": category.get("group_description"),
    }

    return transformed


def run_freeagent_categories_etl(access_token: str) -> dict[str, int]:
    """
    Run FreeAgent categories ETL job.

    Args:
        access_token: FreeAgent OAuth access token

    Returns:
        Dict with sync statistics (inserted, updated, total)
    """
    logger.info("Starting FreeAgent categories ETL job")

    # Initialize FreeAgent client
    client = create_freeagent_client(access_token=access_token)

    try:
        # Extract categories from FreeAgent API
        logger.info("Fetching categories from FreeAgent API")
        categories = client.get_categories()

        if not categories:
            logger.info("No categories found")
            return {"inserted": 0, "updated": 0, "total": 0}

        logger.info(f"Retrieved {len(categories)} categories from FreeAgent")

        # Transform categories
        transformed_categories = []
        for category in categories:
            try:
                transformed = transform_category(category)
                if transformed["category_id"]:  # Only include categories with valid IDs
                    transformed_categories.append(transformed)
                else:
                    logger.warning(f"Skipping category with invalid ID: {category}")
            except Exception as e:
                logger.error(f"Error transforming category {category}: {e}")
                continue

        if not transformed_categories:
            logger.warning("No valid categories to upsert after transformation")
            return {"inserted": 0, "updated": 0, "total": 0}

        logger.info(f"Transformed {len(transformed_categories)} valid categories")

        # Load into database
        inserted, updated = upsert_freeagent_categories(transformed_categories)
        total = len(transformed_categories)

        logger.info(
            f"FreeAgent categories ETL completed: {inserted} inserted, {updated} updated, {total} total"
        )

        return {"inserted": inserted, "updated": updated, "total": total}

    except FreeAgentFeatureUnavailableError as e:
        logger.warning(f"Categories feature unavailable: {e}")
        return {"inserted": 0, "updated": 0, "total": 0, "error": "feature_unavailable"}

    except Exception as e:
        logger.error(f"Error in FreeAgent categories ETL: {e}")
        raise


def main():
    """CLI entry point for FreeAgent categories ETL job."""
    parser = argparse.ArgumentParser(description="FreeAgent Categories ETL Job")
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
        result = run_freeagent_categories_etl(access_token=access_token)

        print(f"Categories ETL Result: {result}")
        return 0

    except Exception as e:
        logger.error(f"Failed to run FreeAgent categories ETL: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
