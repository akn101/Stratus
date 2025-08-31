"""
Amazon SP-API Orders client for Stratus ERP Integration Service.

Provides read-only access to Amazon Selling Partner API for order data.
Handles authentication, rate limiting, pagination, and data normalization.
"""

import logging
import os
import time
from datetime import datetime
from decimal import Decimal

import requests
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class AmazonConfig(BaseModel):
    """Amazon SP-API configuration from environment variables."""

    access_token: str = Field(..., description="LWA access token")
    refresh_token: str = Field(..., description="LWA refresh token")
    client_id: str = Field(..., description="LWA client ID")
    client_secret: str = Field(..., description="LWA client secret")
    region: str = Field(default="eu-west-1", description="AWS region")
    endpoint: str = Field(
        default="https://sellingpartnerapi-eu.amazon.com", description="SP-API endpoint"
    )
    marketplace_ids: list[str] = Field(..., description="List of marketplace IDs")

    @classmethod
    def from_env(cls) -> "AmazonConfig":
        """Load configuration from environment variables."""
        marketplace_ids_str = os.getenv("AMZ_MARKETPLACE_IDS", "")
        if not marketplace_ids_str:
            raise ValueError("AMZ_MARKETPLACE_IDS environment variable is required")

        marketplace_ids = [mid.strip() for mid in marketplace_ids_str.split(",") if mid.strip()]

        access_token = os.getenv("AMZ_ACCESS_TOKEN", "")
        refresh_token = os.getenv("AMZ_REFRESH_TOKEN", "")
        client_id = os.getenv("AMZ_CLIENT_ID", "")
        client_secret = os.getenv("AMZ_CLIENT_SECRET", "")
        missing = [
            name
            for name, val in (
                ("AMZ_ACCESS_TOKEN", access_token),
                ("AMZ_REFRESH_TOKEN", refresh_token),
                ("AMZ_CLIENT_ID", client_id),
                ("AMZ_CLIENT_SECRET", client_secret),
            )
            if not val
        ]
        if missing:
            raise ValueError(f"Missing required Amazon env vars: {', '.join(missing)}")

        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            region=os.getenv("AMZ_REGION", "eu-west-1"),
            endpoint=os.getenv("AMZ_ENDPOINT", "https://sellingpartnerapi-eu.amazon.com"),
            marketplace_ids=marketplace_ids,
        )


class AmazonRetryableError(Exception):
    """Retryable error for Amazon HTTP calls (429/5xx or transient network errors)."""


class AmazonOrdersClient:
    """Amazon SP-API Orders client with retry logic and rate limiting."""

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
            requests.HTTPError: For HTTP errors
            ValueError: For API errors
        """
        url = f"{self.config.endpoint}{path}"

        logger.debug(f"Making {method} request to {url} with params: {params}")

        response = self.session.request(method, url, params=params, timeout=30)

        # Log rate limit headers for monitoring
        if "x-amzn-RequestId" in response.headers:
            logger.info(f"Amazon request ID: {response.headers['x-amzn-RequestId']}")

        if "x-amzn-RateLimit-Limit" in response.headers:
            logger.debug(f"Rate limit: {response.headers['x-amzn-RateLimit-Limit']}")

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

    def get_orders_since(
        self, since_iso: str, page_size: int = 100
    ) -> tuple[list[dict], list[dict]]:
        """
        Fetch orders and order items created/updated since the given timestamp.

        Args:
            since_iso: ISO 8601 timestamp (e.g., "2023-01-01T00:00:00Z")
            page_size: Number of orders per page (max 100)

        Returns:
            Tuple of (orders_list, order_items_list) normalized for our schema
        """
        orders = []
        order_items = []
        next_token = None

        logger.info(f"Fetching Amazon orders since {since_iso}")

        while True:
            params = {
                "MarketplaceIds": ",".join(self.config.marketplace_ids),
                "LastUpdatedAfter": since_iso,
                "OrderStatuses": "Pending,Unshipped,PartiallyShipped,Shipped,Canceled,Unfulfillable",
                "MaxResultsPerPage": min(page_size, 100),
            }

            if next_token:
                params["NextToken"] = next_token

            try:
                response_data = self._make_request("GET", "/orders/v0/orders", params)

                orders_payload = response_data.get("payload", {})
                orders_list = orders_payload.get("Orders", [])

                logger.info(f"Retrieved {len(orders_list)} orders from Amazon")

                # Process each order
                for order_data in orders_list:
                    # Normalize order data
                    normalized_order = self._normalize_order(order_data)
                    orders.append(normalized_order)

                    # Fetch order items for this order
                    order_id = order_data.get("AmazonOrderId")
                    if order_id:
                        items = self._get_order_items(order_id)
                        order_items.extend(items)

                # Check for pagination
                next_token = orders_payload.get("NextToken")
                if not next_token:
                    break

                # Rate limiting - be conservative
                time.sleep(1)

            except Exception as e:
                logger.error(f"Error fetching orders: {e}")
                raise

        logger.info(f"Total orders retrieved: {len(orders)}, total items: {len(order_items)}")
        return orders, order_items

    def _get_order_items(self, order_id: str) -> list[dict]:
        """
        Fetch order items for a specific order.

        Args:
            order_id: Amazon order ID

        Returns:
            List of normalized order items
        """
        try:
            response_data = self._make_request("GET", f"/orders/v0/orders/{order_id}/orderItems")

            items_payload = response_data.get("payload", {})
            items_list = items_payload.get("OrderItems", [])

            normalized_items = []
            for item_data in items_list:
                normalized_item = self._normalize_order_item(order_id, item_data)
                normalized_items.append(normalized_item)

            return normalized_items

        except Exception as e:
            logger.error(f"Error fetching items for order {order_id}: {e}")
            # Return empty list to avoid breaking the entire sync
            return []

    def _normalize_order(self, order_data: dict) -> dict:
        """
        Normalize Amazon order data to match our database schema.

        Args:
            order_data: Raw order data from Amazon API

        Returns:
            Normalized order dictionary
        """
        # Parse total amount
        total_amount = None
        if "OrderTotal" in order_data and order_data["OrderTotal"]:
            amount_str = order_data["OrderTotal"].get("Amount", "0")
            try:
                total_amount = Decimal(amount_str)
            except (ValueError, TypeError):
                logger.warning(f"Invalid total amount: {amount_str}")

        # Parse purchase date
        purchase_date_str = order_data.get("PurchaseDate", "")
        try:
            purchase_date = datetime.fromisoformat(purchase_date_str.replace("Z", "+00:00"))
        except ValueError:
            logger.warning(f"Invalid purchase date: {purchase_date_str}")
            purchase_date = datetime.utcnow()

        return {
            "order_id": order_data.get("AmazonOrderId"),
            "source": "amazon",
            "purchase_date": purchase_date,
            "status": order_data.get("OrderStatus"),
            "customer_id": order_data.get("BuyerEmail", ""),  # May be anonymized
            "total": total_amount,
            "currency": order_data.get("OrderTotal", {}).get("CurrencyCode")
            if order_data.get("OrderTotal")
            else None,
            "marketplace_id": order_data.get("MarketplaceId"),
        }

    def _normalize_order_item(self, order_id: str, item_data: dict) -> dict:
        """
        Normalize Amazon order item data to match our database schema.

        Args:
            order_id: Amazon order ID
            item_data: Raw item data from Amazon API

        Returns:
            Normalized order item dictionary
        """
        # Parse price
        price = None
        if "ItemPrice" in item_data and item_data["ItemPrice"]:
            amount_str = item_data["ItemPrice"].get("Amount", "0")
            try:
                price = Decimal(amount_str)
            except (ValueError, TypeError):
                logger.warning(f"Invalid item price: {amount_str}")

        # Parse tax
        tax = None
        if "ItemTax" in item_data and item_data["ItemTax"]:
            tax_str = item_data["ItemTax"].get("Amount", "0")
            try:
                tax = Decimal(tax_str)
            except (ValueError, TypeError):
                logger.warning(f"Invalid item tax: {tax_str}")

        return {
            "order_id": order_id,
            "sku": item_data.get("SellerSKU", ""),
            "asin": item_data.get("ASIN", ""),
            "qty": int(item_data.get("QuantityOrdered", 1)),
            "price": price,
            "tax": tax,
            "fee_estimate": None,  # Not available in order items API
        }
