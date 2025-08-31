"""
Amazon SP-API FBA Inventory client for Stratus ERP Integration Service.

Provides read-only access to Amazon FBA inventory summaries for warehouse management.
Handles pagination, rate limiting, and data normalization.
"""

import logging
import time
from collections.abc import Iterator
from datetime import UTC, datetime

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .amazon import AmazonConfig
from .amazon_finance import AmazonRetryableError

logger = logging.getLogger(__name__)


class AmazonInventoryClient:
    """Amazon SP-API FBA Inventory client with pagination and rate limiting."""

    def __init__(self, config: AmazonConfig | None = None):
        self.config = config or AmazonConfig.from_env()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "x-amz-access-token": self.config.access_token,
                "User-Agent": "Stratus-ERP/1.0",
            }
        )

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type(
            (
                AmazonRetryableError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            )
        ),
        reraise=True,
    )
    def _make_request(self, method: str, path: str, params: dict | None = None) -> dict:
        """
        Make authenticated request to Amazon SP-API with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            params: Query parameters

        Returns:
            Response JSON data

        Raises:
            AmazonRetryableError: For retryable errors (rate limits, server errors)
            requests.HTTPError: For non-retryable client errors
        """
        url = f"{self.config.endpoint}{path}"

        logger.debug(f"Making {method} request to {url} with params: {params}")

        response = self.session.request(method, url, params=params, timeout=30)

        # Log request tracking (handle mocked responses lacking headers)
        raw_headers = getattr(response, "headers", None)
        headers = raw_headers if isinstance(raw_headers, dict) else {}
        if "x-amzn-RequestId" in headers:
            logger.info(f"Amazon request ID: {headers['x-amzn-RequestId']}")

        if "x-amzn-RateLimit-Limit" in headers:
            logger.debug(f"Rate limit: {headers['x-amzn-RateLimit-Limit']}")

        # Handle rate limiting
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            logger.warning(f"Rate limited, retrying after {retry_after} seconds")
            time.sleep(retry_after)
            raise AmazonRetryableError("Rate limited")

        # Handle server errors
        if 500 <= response.status_code < 600:
            logger.error(f"Server error {response.status_code}: {response.text}")
            raise AmazonRetryableError(f"Server error: {response.status_code}")

        # Handle client errors
        if 400 <= response.status_code < 500:
            logger.error(f"Client error {response.status_code}: {response.text}")
            response.raise_for_status()

        return response.json()

    def get_fba_inventory_summaries(self, next_token: str | None = None) -> Iterator[dict]:
        """
        Get FBA inventory summaries with pagination support.

        Args:
            next_token: Pagination token for continuing from previous page

        Yields:
            Normalized inventory dictionaries matching our warehouse schema
        """
        logger.info("Fetching FBA inventory summaries from Amazon SP-API")

        params = {
            "marketplaceIds": ",".join(self.config.marketplace_ids),
            "details": "true",  # Include additional details like reserved quantities
            "granularityType": "Marketplace",
            "granularityId": self.config.marketplace_ids[0],  # Use first marketplace as default
            "maxResults": 50,  # Conservative page size to respect rate limits
        }

        if next_token:
            params["nextToken"] = next_token
            logger.debug(f"Continuing pagination with token: {next_token[:20]}...")

        try:
            response_data = self._make_request("GET", "/fba/inventory/v1/summaries", params)

            payload = response_data.get("payload", {})
            inventory_summaries = payload.get("inventorySummaries", [])

            logger.info(f"Retrieved {len(inventory_summaries)} inventory summaries")

            # Normalize and yield each inventory item
            for summary in inventory_summaries:
                normalized_item = self._normalize_inventory_summary(summary)
                if normalized_item:
                    yield normalized_item

            # Check for pagination and recursively fetch next page
            next_token = payload.get("nextToken")
            if next_token:
                logger.debug("Found next page token, continuing pagination")
                time.sleep(1)  # Rate limiting - be conservative
                yield from self.get_fba_inventory_summaries(next_token)

        except Exception as e:
            logger.error(f"Error fetching inventory summaries: {e}")
            raise

    def _normalize_inventory_summary(self, summary: dict) -> dict | None:
        """
        Normalize Amazon inventory summary to match our warehouse schema.

        Args:
            summary: Raw inventory summary from Amazon API

        Returns:
            Normalized inventory dictionary or None if invalid
        """
        try:
            # Extract key identifiers
            sku = summary.get("sellerSku", "").strip()
            if not sku:
                logger.warning(f"Inventory summary missing SKU: {summary}")
                return None

            asin = summary.get("asin", "").strip()
            fnsku = summary.get("fnSku", "").strip()

            # Extract fulfillment center info
            # Note: This is simplified - in practice, you might want to aggregate across FCs
            fulfillment_center = None
            if "fulfillmentCenterDetails" in summary:
                fc_details = summary["fulfillmentCenterDetails"]
                if fc_details and len(fc_details) > 0:
                    fulfillment_center = fc_details[0].get("fulfillmentCenterCode", "")

            # Parse quantity information
            total_quantity = summary.get("totalQuantity", 0)

            # Parse detailed quantities if available
            on_hand = 0
            reserved = 0
            inbound = 0

            # Check for detailed quantity breakdown
            if "inventoryDetails" in summary:
                details = summary["inventoryDetails"]

                # Fulfillable quantity (available for sale)
                fulfillable_qty = details.get("fulfillableQuantity", 0)
                on_hand = max(0, int(fulfillable_qty))

                # Reserved quantity (allocated but not shipped)
                reserved_qty = details.get("reservedQuantity", {})
                if isinstance(reserved_qty, dict):
                    total_reserved = reserved_qty.get("totalReservedQuantity", 0)
                    reserved = max(0, int(total_reserved))
                elif isinstance(reserved_qty, int | str):
                    reserved = max(0, int(reserved_qty))

                # Inbound quantity (in transfer to fulfillment centers)
                inbound_qty = details.get("inboundWorkingQuantity", 0)
                inbound = max(0, int(inbound_qty))
            else:
                # Fallback to total quantity if details not available
                on_hand = max(0, int(total_quantity))

            # Create normalized inventory record
            return {
                "sku": sku,
                "asin": asin or None,
                "fnsku": fnsku or None,
                "fc": fulfillment_center or None,
                "on_hand": on_hand,
                "reserved": reserved,
                "inbound": inbound,
                "updated_at": datetime.now(UTC),
            }

        except (ValueError, KeyError, TypeError) as e:
            logger.warning(f"Error normalizing inventory summary: {e}, summary: {summary}")
            return None

    def get_all_inventory_summaries(self) -> list[dict]:
        """
        Convenience method to get all inventory summaries at once.

        Returns:
            List of all normalized inventory dictionaries
        """
        logger.info("Fetching all FBA inventory summaries")

        all_summaries = []
        for summary in self.get_fba_inventory_summaries():
            all_summaries.append(summary)

        logger.info(f"Retrieved {len(all_summaries)} total inventory summaries")
        return all_summaries
