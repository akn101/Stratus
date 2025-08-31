"""
Tests for Shopify Orders ETL job.

Mocks Shopify Admin API responses and validates data normalization and database operations.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

# Import modules under test
from src.adapters.shopify import ShopifyClient, ShopifyConfig
from src.jobs.shopify_orders import (
    run_shopify_orders_sync,
    validate_orders_data,
)


class TestShopifyClient:
    """Test cases for Shopify API client."""

    @pytest.fixture
    def mock_config(self) -> ShopifyConfig:
        """Create a mock Shopify configuration."""
        return ShopifyConfig(shop="test-shop", access_token="shpat_test123", api_version="2024-07")

    @pytest.fixture
    def mock_orders_response(self) -> dict:
        """Mock Shopify orders API response."""
        return {
            "orders": [
                {
                    "id": 4755551001,
                    "name": "#1001",
                    "created_at": "2023-12-01T10:30:00Z",
                    "updated_at": "2023-12-01T10:35:00Z",
                    "total_price": "29.99",
                    "currency": "USD",
                    "financial_status": "paid",
                    "fulfillment_status": "unfulfilled",
                    "customer": {"id": 123456789, "email": "customer@example.com"},
                    "line_items": [
                        {"id": 11111, "sku": "TEST-PRODUCT-001", "quantity": 2, "price": "14.99"}
                    ],
                },
                {
                    "id": 4755551002,
                    "name": "#1002",
                    "created_at": "2023-12-01T14:15:00Z",
                    "updated_at": "2023-12-01T14:20:00Z",
                    "total_price": "45.50",
                    "currency": "USD",
                    "financial_status": "pending",
                    "fulfillment_status": None,
                    "customer": {"id": 987654321, "email": "another@example.com"},
                    "line_items": [
                        {"id": 22222, "sku": "TEST-PRODUCT-002", "quantity": 1, "price": "45.50"}
                    ],
                },
            ]
        }

    @patch("src.adapters.shopify.requests.Session")
    def test_normalize_order(self, mock_session, mock_config, mock_orders_response):
        """Test order data normalization."""
        client = ShopifyClient(mock_config)

        order_data = mock_orders_response["orders"][0]
        normalized = client._normalize_order(order_data)

        assert normalized["order_id"] == "4755551001"
        assert normalized["source"] == "shopify"
        assert normalized["status"] == "paid"
        assert normalized["customer_id"] == "123456789"
        assert normalized["total"] == Decimal("29.99")
        assert normalized["currency"] == "USD"
        assert normalized["marketplace_id"] is None
        assert isinstance(normalized["purchase_date"], datetime)

    @patch("src.adapters.shopify.requests.Session")
    def test_normalize_order_item(self, mock_session, mock_config):
        """Test order line item data normalization."""
        client = ShopifyClient(mock_config)

        item_data = {"id": 11111, "sku": "TEST-PRODUCT-001", "quantity": 2, "price": "14.99"}

        normalized = client._normalize_order_item("4755551001", item_data)

        assert normalized["order_id"] == "4755551001"
        assert normalized["sku"] == "TEST-PRODUCT-001"
        assert normalized["asin"] is None
        assert normalized["qty"] == 2
        assert normalized["price"] == Decimal("14.99")
        assert normalized["tax"] is None
        assert normalized["fee_estimate"] is None

    @patch("src.adapters.shopify.requests.Session")
    def test_get_orders_since(self, mock_session, mock_config, mock_orders_response):
        """Test fetching orders with mocked API response."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_orders_response
        mock_session.return_value.request.return_value = mock_response

        client = ShopifyClient(mock_config)
        orders, order_items = client.get_orders_since("2023-12-01T00:00:00Z")

        # Verify results
        assert len(orders) == 2
        assert len(order_items) == 2

        # Verify first order
        first_order = orders[0]
        assert first_order["order_id"] == "4755551001"
        assert first_order["source"] == "shopify"
        assert first_order["total"] == Decimal("29.99")

        # Verify first order item
        first_item = order_items[0]
        assert first_item["order_id"] == "4755551001"
        assert first_item["sku"] == "TEST-PRODUCT-001"
        assert first_item["qty"] == 2


class TestShopifyOrdersJob:
    """Test cases for the Shopify orders ETL job."""

    def test_validate_orders_data_valid(self):
        """Test validation with valid orders data."""
        orders = [
            {
                "order_id": "4755551001",
                "source": "shopify",
                "purchase_date": datetime.now(UTC),
                "status": "paid",
                "customer_id": "123456789",
                "total": Decimal("29.99"),
                "currency": "USD",
                "marketplace_id": None,
            }
        ]

        order_items = [
            {
                "order_id": "4755551001",
                "sku": "TEST-PRODUCT-001",
                "asin": None,
                "qty": 2,
                "price": Decimal("14.99"),
                "tax": None,
                "fee_estimate": None,
            }
        ]

        # Should not raise any exceptions
        validate_orders_data(orders, order_items)

    def test_validate_orders_data_missing_order_id(self):
        """Test validation fails with missing order_id."""
        orders = [{"source": "shopify", "purchase_date": datetime.now(UTC)}]
        order_items = []

        with pytest.raises(ValueError, match="Order missing order_id"):
            validate_orders_data(orders, order_items)

    def test_validate_orders_data_invalid_qty(self):
        """Test validation fails with invalid quantity."""
        orders = [
            {"order_id": "4755551001", "source": "shopify", "purchase_date": datetime.now(UTC)}
        ]

        order_items = [{"order_id": "4755551001", "sku": "TEST-PRODUCT-001", "qty": -1}]

        with pytest.raises(ValueError, match="Order item has invalid qty"):
            validate_orders_data(orders, order_items)

    @patch("src.jobs.shopify_orders.ShopifyClient")
    @patch("src.jobs.shopify_orders.upsert_orders")
    @patch("src.jobs.shopify_orders.upsert_order_items")
    @patch("src.jobs.shopify_orders.get_session")
    def test_run_shopify_orders_sync_success(
        self, mock_get_session, mock_upsert_items, mock_upsert_orders, mock_client_class
    ):
        """Test successful Shopify orders sync job execution."""
        # Mock client and its methods
        mock_client = Mock()
        mock_client.get_orders_since.return_value = (
            [  # Mock orders
                {
                    "order_id": "4755551001",
                    "source": "shopify",
                    "purchase_date": datetime.now(UTC),
                    "status": "paid",
                    "customer_id": "123456789",
                    "total": Decimal("29.99"),
                    "currency": "USD",
                    "marketplace_id": None,
                }
            ],
            [  # Mock order items
                {
                    "order_id": "4755551001",
                    "sku": "TEST-PRODUCT-001",
                    "asin": None,
                    "qty": 2,
                    "price": Decimal("14.99"),
                    "tax": None,
                    "fee_estimate": None,
                }
            ],
        )
        mock_client_class.return_value = mock_client

        # Mock database operations
        mock_upsert_orders.return_value = (1, 0)  # 1 inserted, 0 updated
        mock_upsert_items.return_value = (1, 0)  # 1 inserted, 0 updated

        # Mock session context manager
        mock_session = Mock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Run the sync job
        stats = run_shopify_orders_sync()

        # Verify results
        assert stats["orders_processed"] == 1
        assert stats["orders_inserted"] == 1
        assert stats["orders_updated"] == 0
        assert stats["items_processed"] == 1
        assert stats["items_inserted"] == 1
        assert stats["items_updated"] == 0

        # Verify database operations were called
        mock_upsert_orders.assert_called_once()
        mock_upsert_items.assert_called_once()

    @patch("src.jobs.shopify_orders.ShopifyClient")
    def test_run_shopify_orders_sync_no_orders(self, mock_client_class):
        """Test sync job with no orders returned."""
        # Mock client returning empty results
        mock_client = Mock()
        mock_client.get_orders_since.return_value = ([], [])
        mock_client_class.return_value = mock_client

        # Run the sync job
        stats = run_shopify_orders_sync()

        # Verify results
        assert stats["orders_processed"] == 0
        assert stats["orders_inserted"] == 0
        assert stats["orders_updated"] == 0
        assert stats["items_processed"] == 0
        assert stats["items_inserted"] == 0
        assert stats["items_updated"] == 0
