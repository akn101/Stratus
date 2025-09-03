"""
ShipBob API client for Stratus ERP Integration Service.

Provides read-only access to ShipBob API for inventory levels and order fulfillment data.
Handles authentication, rate limiting, pagination, and data normalization.
"""

import json
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import requests
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class ShipBobConfig(BaseModel):
    """ShipBob API configuration from environment variables."""

    token: str = Field(..., description="ShipBob API token (PAT or OAuth)")
    base_url: str = Field(
        default="https://api.shipbob.com/2025-07", description="ShipBob API base URL"
    )

    @classmethod
    def from_env(cls) -> "ShipBobConfig":
        """Load configuration from environment variables."""
        token = os.getenv("SHIPBOB_TOKEN", "")
        base_url = os.getenv("SHIPBOB_BASE", "https://api.shipbob.com/2025-07")

        if not token:
            raise ValueError("SHIPBOB_TOKEN environment variable is required")

        return cls(token=token, base_url=base_url)


class ShipBobRateLimitError(Exception):
    """Rate limit error for ShipBob API calls."""


class ShipBobClient:
    """ShipBob API client with pagination and rate limiting."""

    def __init__(self, config: ShipBobConfig | None = None):
        """Initialize ShipBob client."""
        self.config = config or ShipBobConfig.from_env()
        self.session = requests.Session()

        # Set up authentication headers
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.config.token}",
                "Content-Type": "application/json",
                "User-Agent": "Stratus-ERP-Integration/1.0",
            }
        )

    def _handle_rate_limiting(self, response: requests.Response) -> None:
        """Handle rate limiting based on response."""
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            logger.warning(f"ShipBob rate limit hit, waiting {retry_after} seconds")
            time.sleep(retry_after)
            raise ShipBobRateLimitError("Rate limit exceeded")

        # Proactive rate limiting based on headers (if available)
        # ShipBob doesn't specify rate limit headers in the API spec, so we use conservative approach
        time.sleep(0.5)  # Conservative delay between requests

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(
            (
                ShipBobRateLimitError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            )
        ),
        reraise=True,
    )
    def _make_request(self, method: str, endpoint: str, params: dict = None) -> dict:
        """Make authenticated request to ShipBob API with retry logic."""
        url = f"{self.config.base_url}{endpoint}"

        logger.debug(f"ShipBob API request: {method} {url}")

        response = self.session.request(method, url, params=params or {}, timeout=30)

        # Handle rate limiting
        self._handle_rate_limiting(response)

        # Check for API errors
        if 500 <= response.status_code < 600:
            logger.error(f"ShipBob server error {response.status_code}: {response.text}")
            raise ShipBobRateLimitError(f"Server error: {response.status_code}")
        if response.status_code == 401:
            raise ValueError("ShipBob authentication failed - check SHIPBOB_TOKEN")
        elif response.status_code == 403:
            raise ValueError("ShipBob access denied - check token permissions")
        elif response.status_code >= 400:
            try:
                error_data = response.json()
                logger.error(f"ShipBob API error: {response.status_code} - {error_data}")
            except:
                logger.error(f"ShipBob API error: {response.status_code} - {response.text}")
            response.raise_for_status()

        return response.json()

    def _paginate_all(self, endpoint: str, params: dict = None) -> list[dict]:
        """Fetch all pages from a paginated ShipBob endpoint."""
        all_items = []
        cursor = None
        page_count = 0

        while True:
            current_params = params.copy() if params else {}
            if cursor:
                # Handle different cursor formats
                if cursor.startswith('http'):
                    # Full URL cursor - extract just the cursor parameter
                    from urllib.parse import urlparse, parse_qs
                    parsed = urlparse(cursor)
                    query_params = parse_qs(parsed.query)
                    if 'cursor' in query_params:
                        current_params["Cursor"] = query_params['cursor'][0]
                    else:
                        # If no cursor in URL, try using numeric part
                        cursor_parts = cursor.split('cursor=')
                        if len(cursor_parts) > 1:
                            current_params["Cursor"] = cursor_parts[1].split('&')[0]
                        else:
                            logger.warning(f"Cannot parse cursor URL: {cursor}")
                            break
                else:
                    # Simple cursor token
                    current_params["Cursor"] = cursor

            logger.debug(f"Fetching ShipBob page {page_count + 1} from {endpoint}")

            try:
                response_data = self._make_request("GET", endpoint, current_params)
            except Exception as e:
                logger.error(f"Failed to fetch page {page_count + 1} from {endpoint}: {e}")
                # If this is not the first page, return what we have
                if page_count > 0:
                    logger.warning(f"Stopping pagination at page {page_count} due to error")
                    break
                # If first page fails, re-raise the error
                raise

            # Extract items from response - some endpoints return lists directly
            if isinstance(response_data, list):
                items = response_data
                all_items.extend(items)
            else:
                items = response_data.get("items", [])
                all_items.extend(items)

            logger.info(
                f"Fetched {len(items)} items from ShipBob {endpoint}, total: {len(all_items)}"
            )

            # Check for next page
            if isinstance(response_data, list):
                # For list responses, no pagination
                break
            else:
                cursor = response_data.get("next")
                if not cursor or not items:  # Stop if no cursor or no items
                    break

            page_count += 1

            # Safety check to prevent infinite loops
            if page_count > 1000:
                logger.warning(f"ShipBob pagination safety limit reached for {endpoint}")
                break

        logger.info(f"Completed ShipBob pagination: {len(all_items)} total items from {endpoint}")
        return all_items

    def _normalize_inventory_item(self, item_data: dict) -> dict:
        """Normalize inventory item data to warehouse schema."""
        return {
            "sku": str(item_data.get("sku", "")),
            "quantity_on_hand": item_data.get("total_on_hand_quantity", 0),
            "quantity_available": item_data.get("total_sellable_quantity", 0),
            "quantity_reserved": item_data.get("total_committed_quantity", 0),
            "quantity_incoming": item_data.get("total_awaiting_quantity", 0),
            "last_updated": datetime.now(UTC),
            # Additional ShipBob-specific quantities for reference
            "fulfillable_quantity": item_data.get("total_fulfillable_quantity", 0),
            "backordered_quantity": item_data.get("total_backordered_quantity", 0),
            "exception_quantity": item_data.get("total_exception_quantity", 0),
            "internal_transfer_quantity": item_data.get("total_internal_transfer_quantity", 0),
        }

    def _normalize_order_status(self, order_data: dict, since_iso: str) -> dict | None:
        """Normalize order data to extract status and tracking info."""
        # Parse the since_iso to compare update times
        try:
            since_dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
        except:
            since_dt = datetime.now(UTC) - timedelta(hours=24)

        # Check if order has been updated since the cutoff
        last_update_str = order_data.get("last_updated_date") or order_data.get("created_date")
        if not last_update_str:
            return None

        try:
            last_update_dt = datetime.fromisoformat(last_update_str.replace("Z", "+00:00"))
            if last_update_dt < since_dt:
                return None  # Skip orders not updated since cutoff
        except:
            return None

        # Extract reference_id (external order ID from e-commerce platform)
        reference_id = order_data.get("reference_id")
        if not reference_id:
            return None  # Skip orders without external reference

        # Extract tracking info from shipments
        tracking_info = None
        shipment_status = None

        shipments = order_data.get("shipments", [])
        if shipments:
            # Use the most recent shipment
            latest_shipment = shipments[-1]  # Assume last is most recent
            shipment_status = latest_shipment.get("status")

            tracking_data = latest_shipment.get("tracking", {})
            if tracking_data and tracking_data.get("tracking_number"):
                tracking_info = {
                    "tracking_number": tracking_data.get("tracking_number"),
                    "carrier": tracking_data.get("carrier"),
                    "tracking_url": tracking_data.get("tracking_url"),
                }

        # Map ShipBob status to our normalized status
        shipbob_status = order_data.get("status", "")
        normalized_status = self._map_order_status(shipbob_status, shipment_status)

        return {
            "order_id": reference_id,  # Use external reference as order_id
            "status": normalized_status,
            "tracking": tracking_info,
            "updated_at": last_update_dt,
            "shipbob_order_id": str(order_data.get("id", "")),
            "shipbob_status": shipbob_status,
            "shipment_status": shipment_status,
        }

    def _map_order_status(self, order_status: str, shipment_status: str = None) -> str:
        """Map ShipBob order/shipment status to normalized status."""
        # Prioritize shipment status if available
        if shipment_status:
            shipment_mapping = {
                "Shipped": "shipped",
                "Delivered": "delivered",
                "Processing": "processing",
                "Exception": "exception",
                "Cancelled": "cancelled",
            }
            if shipment_status in shipment_mapping:
                return shipment_mapping[shipment_status]

        # Fall back to order status
        order_mapping = {
            "Processing": "processing",
            "Shipped": "shipped",
            "Complete": "delivered",
            "Cancelled": "cancelled",
            "Exception": "exception",
        }

        return order_mapping.get(order_status, "unknown")

    def get_inventory(self) -> list[dict]:
        """
        Get current inventory levels from ShipBob.

        Returns:
            List of normalized inventory records
        """
        logger.info("Fetching inventory levels from ShipBob")

        # Use inventory-level endpoint for current stock levels
        inventory_items = self._paginate_all("/inventory-level")

        # Normalize to our warehouse schema
        normalized_inventory = []
        for item in inventory_items:
            try:
                normalized = self._normalize_inventory_item(item)
                # Only include items with valid SKUs
                if normalized["sku"]:
                    normalized_inventory.append(normalized)
            except Exception as e:
                logger.warning(
                    f"Failed to normalize ShipBob inventory item {item.get('inventory_id')}: {e}"
                )
                continue

        logger.info(f"Normalized {len(normalized_inventory)} ShipBob inventory items")
        return normalized_inventory
    
    def get_inventory_by_fulfillment_center(self) -> list[dict]:
        """
        Get detailed inventory breakdown by fulfillment center.
        
        Returns:
            List of inventory records with fulfillment center details
        """
        logger.info("Fetching inventory breakdown by fulfillment center")
        
        # Get detailed inventory with location information
        params = {"IncludeFullfillmentCenterDetails": "true"}
        
        try:
            inventory_data = self._paginate_all("/inventory-level", params)
        except Exception as e:
            logger.error(f"Failed to fetch inventory by fulfillment center: {e}")
            return []
        
        logger.info(f"Retrieved {len(inventory_data)} inventory records with fulfillment center details")
        
        # Normalize inventory data with fulfillment center breakdown
        normalized_inventory = []
        for inv_data in inventory_data:
            try:
                # Get base inventory info
                base_inventory = {
                    "sku": inv_data.get("inventory", {}).get("name", ""),
                    "inventory_id": str(inv_data.get("inventory", {}).get("id", "")),
                }
                
                # Process each fulfillment center location
                locations = inv_data.get("fulfillment_center_locations", [])
                if not locations:
                    # Single location (aggregated)
                    normalized = self._normalize_inventory_item(inv_data)
                    normalized.update(base_inventory)
                    normalized_inventory.append(normalized)
                else:
                    # Multiple fulfillment centers
                    for location in locations:
                        location_inventory = base_inventory.copy()
                        location_inventory.update({
                            "fulfillment_center_id": str(location.get("fulfillment_center", {}).get("id", "")),
                            "fulfillment_center_name": location.get("fulfillment_center", {}).get("name", ""),
                            "quantity_on_hand": location.get("quantity_on_hand", 0),
                            "quantity_available": location.get("quantity_available", 0),
                            "quantity_reserved": location.get("quantity_committed", 0),
                            "quantity_incoming": location.get("quantity_incoming", 0),
                            "fulfillable_quantity": location.get("quantity_fulfillable", 0),
                            "backordered_quantity": location.get("quantity_backordered", 0),
                            "exception_quantity": location.get("quantity_exception", 0),
                            "internal_transfer_quantity": location.get("quantity_internal_transfer", 0),
                        })
                        normalized_inventory.append(location_inventory)
                        
            except Exception as e:
                logger.warning(f"Failed to normalize inventory record: {e}")
                continue
        
        logger.info(f"Normalized {len(normalized_inventory)} inventory records by fulfillment center")
        return normalized_inventory

    def get_order_statuses(self, since_iso: str) -> list[dict]:
        """
        Get order status updates from ShipBob since a specific datetime.

        Args:
            since_iso: ISO format datetime string to fetch updates since

        Returns:
            List of order status updates with tracking info
        """
        logger.info(f"Fetching ShipBob order statuses since {since_iso}")

        # Convert ISO string to datetime for API parameters
        try:
            since_dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
        except:
            logger.error(f"Invalid since_iso format: {since_iso}")
            return []

        # Fetch orders updated since the given time
        params = {
            "LastUpdateStartDate": since_dt.isoformat(),
            "HasTracking": "true",  # Focus on orders with tracking info
        }

        orders = self._paginate_all("/order", params)

        # Normalize and filter order status updates
        status_updates = []
        for order in orders:
            try:
                normalized = self._normalize_order_status(order, since_iso)
                if normalized:
                    status_updates.append(normalized)
            except Exception as e:
                logger.warning(f"Failed to normalize ShipBob order {order.get('id')}: {e}")
                continue

        logger.info(f"Found {len(status_updates)} ShipBob order status updates")
        return status_updates

    def get_returns(self, since_iso: str = None) -> list[dict]:
        """
        Get return orders from ShipBob, optionally filtered by date.

        Args:
            since_iso: ISO format datetime string to fetch returns since (optional)

        Returns:
            List of normalized return records
        """
        logger.info("Fetching ShipBob returns" + (f" since {since_iso}" if since_iso else ""))

        params = {}
        if since_iso:
            try:
                since_dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
                params["StartDate"] = since_dt.isoformat()
            except:
                logger.warning(f"Invalid since_iso format: {since_iso}")

        try:
            returns = self._paginate_all("/return", params)
        except Exception as e:
            logger.warning(f"Failed to paginate /return endpoint: {e}")
            # Try direct request without pagination
            try:
                returns = self._make_request("GET", "/return", params)
                if isinstance(returns, dict):
                    returns = returns.get("items", [])
            except Exception as e2:
                logger.error(f"Failed to fetch returns: {e2}")
                return []

        # Normalize return data
        normalized_returns = []
        for return_data in returns:
            try:
                normalized = self._normalize_return(return_data)
                if normalized:
                    normalized_returns.append(normalized)
            except Exception as e:
                logger.warning(f"Failed to normalize ShipBob return {return_data.get('id')}: {e}")
                continue

        logger.info(f"Normalized {len(normalized_returns)} ShipBob return records")
        return normalized_returns

    def get_receiving_orders(self, since_iso: str = None) -> list[dict]:
        """
        Get warehouse receiving orders (WROs) from ShipBob.

        Args:
            since_iso: ISO format datetime string to fetch WROs since (optional)

        Returns:
            List of normalized receiving order records
        """
        logger.info(
            "Fetching ShipBob receiving orders" + (f" since {since_iso}" if since_iso else "")
        )

        params = {}
        if since_iso:
            try:
                since_dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
                params["InsertStartDate"] = since_dt.isoformat()
            except:
                logger.warning(f"Invalid since_iso format: {since_iso}")

        try:
            receiving_orders = self._paginate_all("/receiving", params)
        except Exception as e:
            logger.warning(f"Failed to paginate /receiving endpoint: {e}")
            # Try direct request without pagination
            try:
                receiving_orders = self._make_request("GET", "/receiving", params)
                if isinstance(receiving_orders, dict):
                    receiving_orders = receiving_orders.get("items", [])
            except Exception as e2:
                logger.error(f"Failed to fetch receiving orders: {e2}")
                return []

        # Normalize receiving order data
        normalized_wros = []
        for wro_data in receiving_orders:
            try:
                normalized = self._normalize_receiving_order(wro_data)
                if normalized:
                    normalized_wros.append(normalized)
            except Exception as e:
                logger.warning(f"Failed to normalize ShipBob WRO {wro_data.get('id')}: {e}")
                continue

        logger.info(f"Normalized {len(normalized_wros)} ShipBob receiving order records")
        return normalized_wros

    def get_products(self) -> tuple[list[dict], list[dict]]:
        """
        Get products and their variants from ShipBob.

        Returns:
            Tuple of (products, variants) lists
        """
        logger.info("Fetching ShipBob products")

        products_data = self._paginate_all("/product")

        products = []
        variants = []

        for product_data in products_data:
            try:
                # Normalize product
                normalized_product = self._normalize_shipbob_product(product_data)
                products.append(normalized_product)

                # Get variants for this product
                product_id = str(product_data.get("id", ""))
                if product_id:
                    try:
                        variant_response = self._make_request(
                            "GET", f"/product/{product_id}/variants"
                        )
                        # Handle response format - can be list or dict
                        if isinstance(variant_response, list):
                            product_variants = variant_response
                        else:
                            product_variants = variant_response.get("items", [])

                        for variant_data in product_variants:
                            normalized_variant = self._normalize_shipbob_variant(
                                product_id, variant_data
                            )
                            variants.append(normalized_variant)
                    except Exception as e:
                        logger.warning(f"Failed to fetch variants for product {product_id}: {e}")

            except Exception as e:
                logger.warning(f"Failed to normalize ShipBob product {product_data.get('id')}: {e}")
                continue

        logger.info(f"Normalized {len(products)} ShipBob products and {len(variants)} variants")
        return products, variants

    def get_fulfillment_centers(self) -> list[dict]:
        """
        Get fulfillment center information from ShipBob.

        Returns:
            List of normalized fulfillment center records
        """
        logger.info("Fetching ShipBob fulfillment centers")

        response_data = self._make_request("GET", "/fulfillment-center")

        # The response is a direct array, not paginated
        centers_data = response_data if isinstance(response_data, list) else []

        # Normalize fulfillment center data
        normalized_centers = []
        for center_data in centers_data:
            try:
                normalized = self._normalize_fulfillment_center(center_data)
                normalized_centers.append(normalized)
            except Exception as e:
                logger.warning(
                    f"Failed to normalize fulfillment center {center_data.get('id')}: {e}"
                )
                continue

        logger.info(f"Normalized {len(normalized_centers)} ShipBob fulfillment centers")
        return normalized_centers

    def _normalize_return(self, return_data: dict) -> dict:
        """Normalize return order data to warehouse schema."""
        return_items = []
        inventory = return_data.get("inventory", [])
        for item in inventory:
            return_items.append(
                {
                    "inventory_id": str(item.get("id", "")),
                    "name": item.get("name", ""),
                    "quantity": item.get("quantity", 0),
                    "action_requested": item.get("action_requested", {}).get("action", ""),
                    "action_instructions": item.get("action_requested", {}).get("instructions", ""),
                }
            )

        # Calculate total invoice amount from transactions
        transactions = return_data.get("transactions", [])
        total_cost = sum(Decimal(str(t.get("amount", 0))) for t in transactions)

        return {
            "return_id": str(return_data.get("id", "")),
            "source": "shipbob",
            "original_shipment_id": str(return_data.get("original_shipment_id", "")),
            "reference_id": return_data.get("reference_id", ""),
            "store_order_id": return_data.get("store_order_id", ""),
            "status": return_data.get("status", ""),
            "return_type": return_data.get("return_type", ""),
            "customer_name": return_data.get("customer_name", ""),
            "tracking_number": return_data.get("tracking_number", ""),
            "total_cost": total_cost,
            "fulfillment_center_id": str(return_data.get("fulfillment_center", {}).get("id", "")),
            "fulfillment_center_name": return_data.get("fulfillment_center", {}).get("name", ""),
            "items": json.dumps(return_items),
            "transactions": json.dumps(transactions),
            "insert_date": self._parse_datetime(return_data.get("insert_date")),
            "completed_date": self._parse_datetime(return_data.get("completed_date")),
            "created_at": datetime.now(UTC),
        }

    def _normalize_receiving_order(self, wro_data: dict) -> dict:
        """Normalize warehouse receiving order data."""
        inventory_quantities = []
        for item in wro_data.get("inventory_quantities", []):
            inventory_quantities.append(
                {
                    "inventory_id": str(item.get("inventory_id", "")),
                    "sku": item.get("sku", ""),
                    "expected_quantity": item.get("expected_quantity", 0),
                    "received_quantity": item.get("received_quantity", 0),
                    "stowed_quantity": item.get("stowed_quantity", 0),
                }
            )

        return {
            "wro_id": str(wro_data.get("id", "")),
            "source": "shipbob",
            "purchase_order_number": wro_data.get("purchase_order_number", ""),
            "status": wro_data.get("status", ""),
            "package_type": wro_data.get("package_type", ""),
            "box_packaging_type": wro_data.get("box_packaging_type", ""),
            "fulfillment_center_id": str(wro_data.get("fulfillment_center", {}).get("id", "")),
            "fulfillment_center_name": wro_data.get("fulfillment_center", {}).get("name", ""),
            "expected_arrival_date": self._parse_datetime(wro_data.get("expected_arrival_date")),
            "insert_date": self._parse_datetime(wro_data.get("insert_date")),
            "last_updated_date": self._parse_datetime(wro_data.get("last_updated_date")),
            "inventory_quantities": json.dumps(inventory_quantities),
            "status_history": json.dumps(wro_data.get("status_history", [])),
            "created_at": datetime.now(UTC),
        }

    def _normalize_shipbob_product(self, product_data: dict) -> dict:
        """Normalize ShipBob product data."""
        import json
        return {
            "product_id": str(product_data.get("id", "")),
            "source": "shipbob",
            "name": product_data.get("name", ""),
            "sku": product_data.get("sku", ""),
            "barcode": product_data.get("barcode", ""),
            "description": product_data.get("description", ""),
            "category": product_data.get("category", ""),
            "is_case": str(product_data.get("is_case", False)),
            "is_lot": str(product_data.get("is_lot", False)),
            "is_active": str(product_data.get("variant", {}).get("is_active", True)),
            "is_bundle": str(product_data.get("variant", {}).get("is_bundle", False)),
            "is_digital": str(product_data.get("variant", {}).get("is_digital", False)),
            "is_hazmat": str(product_data.get("variant", {}).get("hazmat", {}).get("is_hazmat", False)),
            "dimensions": json.dumps(product_data.get("dimensions", {})),
            "weight": json.dumps(product_data.get("weight", {})),
            "value": json.dumps(product_data.get("value", {})),
            "created_at": datetime.now(UTC),
        }

    def _normalize_shipbob_variant(self, product_id: str, variant_data: dict) -> dict:
        """Normalize ShipBob product variant data."""
        import json
        return {
            "variant_id": str(variant_data.get("id", "")),
            "product_id": product_id,
            "source": "shipbob",
            "name": variant_data.get("name", ""),
            "sku": variant_data.get("sku", ""),
            "barcode": variant_data.get("barcode", ""),
            "is_active": str(variant_data.get("is_active", True)),
            "dimensions": json.dumps(variant_data.get("dimensions", {})),
            "weight": json.dumps(variant_data.get("weight", {})),
            "value": json.dumps(variant_data.get("value", {})),
            "created_at": datetime.now(UTC),
        }

    def _normalize_fulfillment_center(self, center_data: dict) -> dict:
        """Normalize fulfillment center data."""
        return {
            "center_id": str(center_data.get("id", "")),
            "source": "shipbob",
            "name": center_data.get("name", ""),
            "address1": center_data.get("address1", ""),
            "address2": center_data.get("address2", ""),
            "city": center_data.get("city", ""),
            "state": center_data.get("state", ""),
            "zip_code": center_data.get("zip_code", ""),
            "country": center_data.get("country", ""),
            "phone_number": center_data.get("phone_number", ""),
            "email": center_data.get("email", ""),
            "timezone": center_data.get("timezone", ""),
            "created_at": datetime.now(UTC),
        }

    def _parse_datetime(self, date_str: str) -> datetime | None:
        """Parse ISO datetime string to datetime object."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except:
            return None

    def get_all_orders(self, limit: int = None) -> list[dict]:
        """
        Get all ShipBob orders for comprehensive analysis using proper pagination.
        
        Args:
            limit: Optional limit on number of orders to fetch
            
        Returns:
            List of normalized ShipBob order records
        """
        logger.info("Fetching all ShipBob orders with pagination")
        
        all_orders = []
        page_size = 50  # ShipBob API appears to have a maximum of 50 orders per page
        current_page = 1
        
        try:
            while True:
                params = {
                    "PageSize": page_size,
                    "Page": current_page
                }
                
                logger.info(f"Fetching page {current_page} with page size {page_size}")
                response_data = self._make_request("GET", "/order", params)
                
                # Handle different response formats
                if isinstance(response_data, list):
                    page_orders = response_data
                elif isinstance(response_data, dict):
                    page_orders = response_data.get("items", [])
                    # Check if this is a paginated response with metadata
                    total_count = response_data.get("totalCount", 0)
                    if current_page == 1 and total_count > 0:
                        logger.info(f"ShipBob API reports {total_count} total orders")
                else:
                    logger.warning(f"Unexpected response format: {type(response_data)}")
                    break
                
                if not page_orders:
                    logger.info(f"No more orders found on page {current_page}")
                    break
                
                all_orders.extend(page_orders)
                logger.info(f"Page {current_page}: Retrieved {len(page_orders)} orders (total: {len(all_orders)})")
                
                # For ShipBob, we need to continue even if we get exactly page_size
                # Only stop if we get 0 orders
                # ShipBob may return exactly 50 orders per page even when there are more
                
                # Apply limit check during pagination if specified
                if limit and len(all_orders) >= limit:
                    all_orders = all_orders[:limit]
                    logger.info(f"Reached specified limit of {limit} orders")
                    break
                    
                current_page += 1
                
                # Safety break to prevent infinite loops
                if current_page > 100:
                    logger.warning("Reached maximum page limit (100) - stopping pagination")
                    break
                    
        except Exception as e:
            logger.error(f"Failed to fetch ShipBob orders: {e}")
            return []
            
        logger.info(f"Retrieved {len(all_orders)} total orders from ShipBob")
        
        # Normalize order data for database storage
        normalized_orders = []
        for order in all_orders:
            try:
                normalized = self._normalize_full_order(order)
                if normalized:
                    normalized_orders.append(normalized)
            except Exception as e:
                logger.warning(f"Failed to normalize ShipBob order {order.get('id', 'unknown')}: {e}")
                continue
        
        logger.info(f"Normalized {len(normalized_orders)} ShipBob orders")
        return normalized_orders

    def _normalize_full_order(self, order_data: dict) -> dict | None:
        """Normalize full order data for database storage."""
        shipbob_order_id = str(order_data.get("id", ""))
        if not shipbob_order_id:
            return None

        # Extract shipment and tracking info
        shipments = order_data.get("shipments", [])
        tracking_number = ""
        carrier = ""
        shipped_date = None
        delivered_date = None
        fulfillment_center_id = ""
        
        # Get tracking from first shipped shipment
        for shipment in shipments:
            if shipment and isinstance(shipment, dict):
                tracking_data = shipment.get("tracking")
                if tracking_data and isinstance(tracking_data, dict):
                    tracking_number = tracking_data.get("tracking_number", "")
                    carrier = tracking_data.get("carrier_name", "")
                
                # Get location info from shipment
                location = shipment.get("location", {})
                if location and isinstance(location, dict):
                    fulfillment_center_id = str(location.get("id", ""))
                
                if shipment.get("shipped_date"):
                    shipped_date = self._parse_datetime(shipment.get("shipped_date"))
                if shipment.get("delivery_date"):
                    delivered_date = self._parse_datetime(shipment.get("delivery_date"))
                
                # Use data from first shipment
                break
        
        # Extract recipient info
        recipient_data = order_data.get("recipient", {})
        if not recipient_data or not isinstance(recipient_data, dict):
            recipient_data = {}
            
        # Get financials for total cost
        financials = order_data.get("financials", {})
        total_cost = 0
        if financials and isinstance(financials, dict):
            total_cost = financials.get("total_price", 0)
        
        return {
            "shipbob_order_id": shipbob_order_id,
            "reference_id": order_data.get("reference_id", ""),
            "status": order_data.get("status", ""),
            "created_date": self._parse_datetime(order_data.get("created_date")),
            "last_updated_date": self._parse_datetime(order_data.get("last_updated_date")),
            "shipped_date": shipped_date,
            "delivered_date": delivered_date,
            "tracking_number": tracking_number,
            "carrier": carrier,
            "recipient_name": recipient_data.get("name", ""),
            "recipient_email": recipient_data.get("email", ""),
            "fulfillment_center_id": fulfillment_center_id,
            "total_weight": 0,  # Would need to calculate from shipments if needed
            "total_cost": total_cost,
            "currency": "USD",  # ShipBob primarily operates in USD
            "shipping_method": order_data.get("shipping_method", "") if isinstance(order_data.get("shipping_method"), str) else "",
            "created_at": datetime.now(UTC),
        }
