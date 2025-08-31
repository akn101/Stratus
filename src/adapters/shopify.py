"""
Shopify API client for Stratus ERP Integration Service.

Provides read-only access to Shopify Admin API for order, customer, and product data.
Handles authentication, rate limiting, pagination, and data normalization.
"""

import logging
import os
import re
import time
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import requests
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class ShopifyConfig(BaseModel):
    """Shopify API configuration from environment variables."""

    shop: str = Field(..., description="Shopify shop name (without .myshopify.com)")
    access_token: str = Field(..., description="Shopify Admin API access token")
    api_version: str = Field(default="2024-07", description="Shopify API version")

    @classmethod
    def from_env(cls) -> "ShopifyConfig":
        """Load configuration from environment variables."""
        shop = os.getenv("SHOPIFY_SHOP", "")
        access_token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

        if not shop:
            raise ValueError("SHOPIFY_SHOP environment variable is required")
        if not access_token:
            raise ValueError("SHOPIFY_ACCESS_TOKEN environment variable is required")

        return cls(
            shop=shop,
            access_token=access_token,
            api_version=os.getenv("SHOPIFY_API_VERSION", "2024-07"),
        )

    @property
    def base_url(self) -> str:
        """Get the base API URL for this shop."""
        return f"https://{self.shop}.myshopify.com/admin/api/{self.api_version}"


class ShopifyRateLimitError(Exception):
    """Retryable error for Shopify API calls (rate limits / transient failures)."""


class ShopifyClient:
    """Shopify Admin API client with pagination and rate limiting."""

    def __init__(self, config: ShopifyConfig | None = None):
        self.config = config or ShopifyConfig.from_env()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": self.config.access_token,
                "User-Agent": "Stratus-ERP/1.0",
            }
        )

    def _extract_rate_limit_info(
        self, response: requests.Response
    ) -> tuple[int | None, int | None]:
        """
        Extract rate limit information from response headers.

        Args:
            response: HTTP response object

        Returns:
            Tuple of (current_calls, call_limit) or (None, None) if not available
        """
        raw_headers = getattr(response, "headers", None)
        headers = raw_headers if isinstance(raw_headers, dict) else {}
        rate_limit_header = headers.get("X-Shopify-Shop-Api-Call-Limit")
        if isinstance(rate_limit_header, str) and rate_limit_header:
            try:
                current, limit = rate_limit_header.split("/")
                return int(current), int(limit)
            except (ValueError, AttributeError):
                pass
        return None, None

    def _handle_rate_limiting(self, current_calls: int | None, call_limit: int | None) -> None:
        """
        Handle rate limiting by adding delays when approaching limits.

        Args:
            current_calls: Current API call count
            call_limit: API call limit
        """
        if current_calls and call_limit:
            usage_ratio = current_calls / call_limit

            if usage_ratio >= 0.9:  # 90% of limit
                sleep_time = 2.0
                logger.warning(f"Rate limit at {usage_ratio:.1%}, sleeping {sleep_time}s")
                time.sleep(sleep_time)
            elif usage_ratio >= 0.7:  # 70% of limit
                time.sleep(0.5)

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type(
            (
                ShopifyRateLimitError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            )
        ),
        reraise=True,
    )
    def _make_request(self, method: str, path: str, params: dict | None = None) -> dict:
        """
        Make authenticated request to Shopify API with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path (relative to base URL)
            params: Query parameters

        Returns:
            Response JSON data

        Raises:
            ShopifyRateLimitError: For rate limit errors
            requests.HTTPError: For other HTTP errors
        """
        url = f"{self.config.base_url}/{path.lstrip('/')}"

        logger.debug(f"Making {method} request to {url} with params: {params}")

        response = self.session.request(method, url, params=params, timeout=30)
        # Expose headers for pagination helpers that read from the session
        try:
            # store a dict to ensure predictable behavior under mocks
            self.session._last_response_headers = dict(response.headers)
        except Exception:
            self.session._last_response_headers = {}

        # Log rate limit information
        current_calls, call_limit = self._extract_rate_limit_info(response)
        if current_calls and call_limit:
            logger.debug(f"API calls: {current_calls}/{call_limit}")

        # Handle rate limiting
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 2))
            logger.warning(f"Rate limited, retrying after {retry_after} seconds")
            time.sleep(retry_after)
            raise ShopifyRateLimitError("Rate limited")

        # Handle server errors
        if 500 <= response.status_code < 600:
            logger.error(f"Server error {response.status_code}: {response.text}")
            # Treat as retryable
            raise ShopifyRateLimitError(f"Server error: {response.status_code}")

        # Handle client errors
        if 400 <= response.status_code < 500:
            logger.error(f"Client error {response.status_code}: {response.text}")
            response.raise_for_status()

        # Handle rate limiting proactively
        self._handle_rate_limiting(current_calls, call_limit)

        return response.json()

    def _parse_link_header(self, link_header: str) -> dict[str, str]:
        """
        Parse Link header for pagination URLs.

        Args:
            link_header: Link header value

        Returns:
            Dictionary with 'next' and/or 'previous' URLs
        """
        links = {}
        if not link_header:
            return links

        # Parse Link header format: <url>; rel="next", <url>; rel="previous"
        for link in link_header.split(","):
            link = link.strip()
            url_match = re.search(r"<([^>]+)>", link)
            rel_match = re.search(r'rel="([^"]+)"', link)

            if url_match and rel_match:
                url = url_match.group(1)
                rel = rel_match.group(1)
                links[rel] = url

        return links

    def _extract_page_info_from_url(self, url: str) -> str | None:
        """
        Extract page_info parameter from pagination URL.

        Args:
            url: Pagination URL containing page_info

        Returns:
            page_info value or None if not found
        """
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        page_info = query_params.get("page_info", [None])
        return page_info[0] if page_info[0] else None

    def get_orders_since(self, since_iso: str) -> tuple[list[dict], list[dict]]:
        """
        Fetch orders and their line items created/updated since the given timestamp.

        Args:
            since_iso: ISO 8601 timestamp (e.g., "2023-01-01T00:00:00Z")

        Returns:
            Tuple of (orders_list, order_items_list) normalized for our schema
        """
        orders = []
        order_items = []
        page_info = None

        logger.info(f"Fetching Shopify orders since {since_iso}")

        while True:
            params = {
                "updated_at_min": since_iso,
                "status": "any",  # Include all order statuses
                "limit": 50,  # Conservative limit for rate limiting
                "fields": "id,name,created_at,updated_at,total_price,currency,customer,line_items,financial_status,fulfillment_status",
            }

            if page_info:
                params["page_info"] = page_info

            try:
                response_data = self._make_request("GET", "orders.json", params)

                orders_list = response_data.get("orders", [])
                logger.info(f"Retrieved {len(orders_list)} orders from Shopify")

                # Process each order and its line items
                for order_data in orders_list:
                    # Normalize order data
                    normalized_order = self._normalize_order(order_data)
                    orders.append(normalized_order)

                    # Process line items
                    line_items = order_data.get("line_items", [])
                    for item_data in line_items:
                        normalized_item = self._normalize_order_item(
                            str(order_data["id"]), item_data
                        )
                        order_items.append(normalized_item)

                # Check for pagination using Link header
                link_header = getattr(self.session, "_last_response_headers", {}).get("Link", "")
                links = self._parse_link_header(link_header)

                if "next" in links:
                    page_info = self._extract_page_info_from_url(links["next"])
                    if page_info:
                        time.sleep(0.5)  # Rate limiting
                        continue

                break

            except Exception as e:
                logger.error(f"Error fetching orders: {e}")
                raise

        logger.info(f"Total orders retrieved: {len(orders)}, total items: {len(order_items)}")
        return orders, order_items

    def get_customers_since(self, since_iso: str) -> list[dict]:
        """
        Fetch customers created/updated since the given timestamp.

        Args:
            since_iso: ISO 8601 timestamp

        Returns:
            List of normalized customer dictionaries
        """
        customers = []
        page_info = None

        logger.info(f"Fetching Shopify customers since {since_iso}")

        while True:
            params = {
                "updated_at_min": since_iso,
                "limit": 50,
                "fields": "id,email,first_name,last_name,created_at,updated_at,total_spent,orders_count,state,tags,last_order_id,last_order_name",
            }

            if page_info:
                params["page_info"] = page_info

            try:
                response_data = self._make_request("GET", "customers.json", params)

                customers_list = response_data.get("customers", [])
                logger.info(f"Retrieved {len(customers_list)} customers from Shopify")

                # Normalize customer data
                for customer_data in customers_list:
                    normalized_customer = self._normalize_customer(customer_data)
                    customers.append(normalized_customer)

                # Check for pagination
                link_header = getattr(self.session, "_last_response_headers", {}).get("Link", "")
                links = self._parse_link_header(link_header)

                if "next" in links:
                    page_info = self._extract_page_info_from_url(links["next"])
                    if page_info:
                        time.sleep(0.5)
                        continue

                break

            except Exception as e:
                logger.error(f"Error fetching customers: {e}")
                raise

        logger.info(f"Total customers retrieved: {len(customers)}")
        return customers

    def get_products(self) -> tuple[list[dict], list[dict]]:
        """
        Fetch all products and their variants.

        Returns:
            Tuple of (products_list, variants_list) normalized for our schema
        """
        products = []
        variants = []
        page_info = None

        logger.info("Fetching Shopify products and variants")

        while True:
            params = {
                "limit": 50,
                "fields": "id,title,vendor,product_type,created_at,updated_at,variants",
            }

            if page_info:
                params["page_info"] = page_info

            try:
                response_data = self._make_request("GET", "products.json", params)

                products_list = response_data.get("products", [])
                logger.info(f"Retrieved {len(products_list)} products from Shopify")

                # Process each product and its variants
                for product_data in products_list:
                    # Normalize product data
                    normalized_product = self._normalize_product(product_data)
                    products.append(normalized_product)

                    # Process variants
                    variants_list = product_data.get("variants", [])
                    for variant_data in variants_list:
                        normalized_variant = self._normalize_variant(
                            str(product_data["id"]), variant_data
                        )
                        variants.append(normalized_variant)

                # Check for pagination
                link_header = getattr(self.session, "_last_response_headers", {}).get("Link", "")
                links = self._parse_link_header(link_header)

                if "next" in links:
                    page_info = self._extract_page_info_from_url(links["next"])
                    if page_info:
                        time.sleep(0.5)
                        continue

                break

            except Exception as e:
                logger.error(f"Error fetching products: {e}")
                raise

        logger.info(f"Total products retrieved: {len(products)}, total variants: {len(variants)}")
        return products, variants

    def _normalize_order(self, order_data: dict) -> dict:
        """Normalize Shopify order data to match our warehouse schema."""
        # Parse total price
        total_amount = None
        total_str = order_data.get("total_price", "0")
        try:
            total_amount = Decimal(total_str)
        except (ValueError, TypeError):
            logger.warning(f"Invalid total price: {total_str}")

        # Parse dates
        created_at_str = order_data.get("created_at", "")
        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except ValueError:
            logger.warning(f"Invalid created_at date: {created_at_str}")
            created_at = datetime.now(UTC)

        # Extract customer ID
        customer = order_data.get("customer", {})
        customer_id = str(customer.get("id", "")) if customer else ""

        # For order_id, use human-readable order name if available, fallback to internal ID
        order_name = order_data.get("name")
        order_id = order_name if order_name else str(order_data["id"])
        
        result = {
            "order_id": order_id,  # Use human-readable order name (e.g., "2121") 
            "purchase_date": created_at,
            "status": order_data.get("financial_status", ""),
            "customer_id": customer_id,
            "total": total_amount,
            "currency": order_data.get("currency", ""),
        }
        
        # Only add shopify_internal_id if it's different from order_id (to avoid redundancy)
        internal_id = str(order_data["id"])
        if internal_id != order_id:
            result["shopify_internal_id"] = internal_id
            
        return result

    def _normalize_order_item(self, order_id: str, item_data: dict) -> dict:
        """Normalize Shopify line item data to match our warehouse schema."""
        # Parse price
        price = None
        price_str = item_data.get("price", "0")
        try:
            price = Decimal(price_str)
        except (ValueError, TypeError):
            logger.warning(f"Invalid item price: {price_str}")

        # Use line item id as fallback key when SKU is missing to preserve uniqueness
        sku = item_data.get("sku") or str(item_data.get("id", ""))
        return {
            "order_id": order_id,
            "sku": sku,
            "asin": None,  # Not applicable for Shopify
            "qty": int(item_data.get("quantity", 1)),
            "price": price,
            "tax": None,  # Could be calculated from tax_lines if needed
            "fee_estimate": None,
        }

    def _normalize_customer(self, customer_data: dict) -> dict:
        """Normalize Shopify customer data."""
        # Parse dates
        created_at_str = customer_data.get("created_at", "")
        updated_at_str = customer_data.get("updated_at", "")

        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except ValueError:
            created_at = datetime.now(UTC)

        try:
            updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        except ValueError:
            updated_at = datetime.now(UTC)

        # Parse total spent
        total_spent = None
        total_spent_str = customer_data.get("total_spent", "0")
        try:
            total_spent = Decimal(total_spent_str)
        except (ValueError, TypeError):
            total_spent = Decimal("0")

        # Parse tags
        tags = customer_data.get("tags", "")
        tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else []

        return {
            "customer_id": str(customer_data["id"]),
            "email": customer_data.get("email", ""),
            "first_name": customer_data.get("first_name", ""),
            "last_name": customer_data.get("last_name", ""),
            "created_at": created_at,
            "updated_at": updated_at,
            "total_spent": total_spent,
            "orders_count": int(customer_data.get("orders_count", 0)),
            "state": customer_data.get("state", ""),
            "tags": tags_list,
            "last_order_id": str(customer_data.get("last_order_id", ""))
            if customer_data.get("last_order_id")
            else None,
            "last_order_date": None,  # Would need to fetch from last order if needed
        }

    def _normalize_product(self, product_data: dict) -> dict:
        """Normalize Shopify product data."""
        # Parse dates
        created_at_str = product_data.get("created_at", "")
        updated_at_str = product_data.get("updated_at", "")

        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except ValueError:
            created_at = datetime.now(UTC)

        try:
            updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        except ValueError:
            updated_at = datetime.now(UTC)

        return {
            "product_id": str(product_data["id"]),
            "title": product_data.get("title", ""),
            "vendor": product_data.get("vendor", ""),
            "product_type": product_data.get("product_type", ""),
            "created_at": created_at,
            "updated_at": updated_at,
        }

    def _normalize_variant(self, product_id: str, variant_data: dict) -> dict:
        """Normalize Shopify variant data."""
        # Parse dates
        created_at_str = variant_data.get("created_at", "")
        updated_at_str = variant_data.get("updated_at", "")

        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except ValueError:
            created_at = datetime.now(UTC)

        try:
            updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        except ValueError:
            updated_at = datetime.now(UTC)

        # Parse price
        price = None
        price_str = variant_data.get("price", "0")
        try:
            price = Decimal(price_str)
        except (ValueError, TypeError):
            logger.warning(f"Invalid variant price: {price_str}")

        return {
            "variant_id": str(variant_data["id"]),
            "product_id": product_id,
            "sku": variant_data.get("sku", ""),
            "price": price,
            "inventory_item_id": str(variant_data.get("inventory_item_id", ""))
            if variant_data.get("inventory_item_id")
            else None,
            "created_at": created_at,
            "updated_at": updated_at,
        }
