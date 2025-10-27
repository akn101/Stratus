#!/usr/bin/env python3
"""
FreeAgent Users ETL Job

Syncs users from FreeAgent API into the data warehouse.
Users represent team members with access to the FreeAgent account.
Users are typically synced once and rarely change.

Usage:
    python -m src.jobs.freeagent_users [--log-level INFO]
"""

import argparse
import logging
from datetime import datetime

from src.adapters.freeagent import FreeAgentFeatureUnavailableError, create_freeagent_client
from src.common.etl import extract_id_from_url, json_serialize, parse_date
from src.db.upserts_source_specific import upsert_freeagent_users
from src.utils.config import get_secret

logger = logging.getLogger(__name__)


def transform_user(user: dict) -> dict:
    """Transform FreeAgent user to database format."""
    # Extract IDs from URLs
    user_id = extract_id_from_url(user.get("url", ""))

    # Parse dates
    created_at_api = parse_date(user.get("created_at"))
    updated_at_api = parse_date(user.get("updated_at"))

    # Handle payroll profile data - store as JSON string if present
    current_payroll_profile = None
    if user.get("current_payroll_profile"):
        try:
            current_payroll_profile = json_serialize(user["current_payroll_profile"])
        except (TypeError, ValueError) as e:
            logger.warning(f"Error serializing payroll profile for user {user_id}: {e}")

    # Transform user data
    transformed = {
        "user_id": user_id,
        "source": "freeagent",
        "email": user.get("email"),
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "ni_number": user.get("ni_number"),
        "unique_tax_reference": user.get("unique_tax_reference"),
        "role": user.get("role"),
        "permission_level": user.get("permission_level"),
        "opening_mileage": user.get("opening_mileage"),
        "current_payroll_profile": current_payroll_profile,
        "created_at_api": created_at_api,
        "updated_at_api": updated_at_api,
    }

    return transformed


def run_freeagent_users_etl(access_token: str) -> dict[str, int]:
    """
    Run FreeAgent users ETL job.

    Args:
        access_token: FreeAgent OAuth access token

    Returns:
        Dict with sync statistics (inserted, updated, total)
    """
    logger.info("Starting FreeAgent users ETL job")

    # Initialize FreeAgent client
    client = create_freeagent_client(access_token=access_token)

    try:
        # Extract users from FreeAgent API
        logger.info("Fetching users from FreeAgent API")
        users = client.get_users()

        if not users:
            logger.info("No users found")
            return {"inserted": 0, "updated": 0, "total": 0}

        logger.info(f"Retrieved {len(users)} users from FreeAgent")

        # Transform users
        transformed_users = []
        for user in users:
            try:
                transformed = transform_user(user)
                if transformed["user_id"]:  # Only include users with valid IDs
                    transformed_users.append(transformed)
                else:
                    logger.warning(f"Skipping user with invalid ID: {user}")
            except Exception as e:
                logger.error(f"Error transforming user {user}: {e}")
                continue

        if not transformed_users:
            logger.warning("No valid users to upsert after transformation")
            return {"inserted": 0, "updated": 0, "total": 0}

        logger.info(f"Transformed {len(transformed_users)} valid users")

        # Load into database
        inserted, updated = upsert_freeagent_users(transformed_users)
        total = len(transformed_users)

        logger.info(
            f"FreeAgent users ETL completed: {inserted} inserted, {updated} updated, {total} total"
        )

        return {"inserted": inserted, "updated": updated, "total": total}

    except FreeAgentFeatureUnavailableError as e:
        logger.warning(f"Users feature unavailable: {e}")
        return {"inserted": 0, "updated": 0, "total": 0, "error": "feature_unavailable"}

    except Exception as e:
        logger.error(f"Error in FreeAgent users ETL: {e}")
        raise


def main():
    """CLI entry point for FreeAgent users ETL job."""
    parser = argparse.ArgumentParser(description="FreeAgent Users ETL Job")
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
        result = run_freeagent_users_etl(access_token=access_token)

        print(f"Users ETL Result: {result}")
        return 0

    except Exception as e:
        logger.error(f"Failed to run FreeAgent users ETL: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
