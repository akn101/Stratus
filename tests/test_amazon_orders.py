"""
Tests for Amazon Orders ETL job.

Mocks Amazon SP-API responses and validates data normalization and database operations.
"""

import os
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

# Import modules under test
from src.adapters.amazon import AmazonConfig, AmazonOrdersClient
from src.jobs.amazon_orders import (
    get_sync_since_timestamp,
    run_amazon_orders_sync,
    validate_orders_data,
)


class TestAmazonOrdersClient:
    """Test cases for Amazon SP-API client."""

    @pytest.fixture
    def mock_config(self) -> AmazonConfig:
        """Create a mock Amazon configuration."""
        return AmazonConfig(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            client_id="test_client_id",
            client_secret="test_client_secret",
            region="eu-west-1",
            endpoint="https://sellingpartnerapi-eu.amazon.com",
            marketplace_ids=["A1F83G8C2ARO7P"],
        )

    @pytest.fixture
    def mock_orders_response(self) -> dict:
        """Mock Amazon orders API response."""
        return {
            "payload": {
                "Orders": [
                    {
                        "AmazonOrderId": "123-4567890-1234567",
                        "PurchaseDate": "2023-12-01T10:30:00Z",
                        "OrderStatus": "Shipped",
                        "BuyerEmail": "buyer@example.com",
                        "MarketplaceId": "A1F83G8C2ARO7P",
                        "OrderTotal": {"Amount": "29.99", "CurrencyCode": "EUR"},
                    },
                    {
                        "AmazonOrderId": "987-6543210-9876543",
                        "PurchaseDate": "2023-12-01T14:15:00Z",
                        "OrderStatus": "Pending",
                        "MarketplaceId": "A1F83G8C2ARO7P",
                        "OrderTotal": {"Amount": "15.50", "CurrencyCode": "EUR"},
                    },
                ]
            }
        }

    @pytest.fixture
    def mock_order_items_response(self) -> dict:
        """Mock Amazon order items API response."""
        return {
            "payload": {
                "OrderItems": [
                    {
                        "ASIN": "B08N5WRWNW",
                        "SellerSKU": "TEST-SKU-001",
                        "QuantityOrdered": 2,
                        "ItemPrice": {"Amount": "25.99", "CurrencyCode": "EUR"},
                        "ItemTax": {"Amount": "4.00", "CurrencyCode": "EUR"},
                    }
                ]
            }
        }

    @patch("src.adapters.amazon.requests.Session")
    def test_normalize_order(self, mock_session, mock_config, mock_orders_response):
        """Test order data normalization."""
        client = AmazonOrdersClient(mock_config)

        order_data = mock_orders_response["payload"]["Orders"][0]
        normalized = client._normalize_order(order_data)

        assert normalized["order_id"] == "123-4567890-1234567"
        assert normalized["source"] == "amazon"
        assert normalized["status"] == "Shipped"
        assert normalized["customer_id"] == "buyer@example.com"
        assert normalized["total"] == Decimal("29.99")
        assert normalized["currency"] == "EUR"
        assert normalized["marketplace_id"] == "A1F83G8C2ARO7P"
        assert isinstance(normalized["purchase_date"], datetime)

    @patch("src.adapters.amazon.requests.Session")
    def test_normalize_order_item(self, mock_session, mock_config, mock_order_items_response):
        """Test order item data normalization."""
        client = AmazonOrdersClient(mock_config)

        order_id = "123-4567890-1234567"
        item_data = mock_order_items_response["payload"]["OrderItems"][0]
        normalized = client._normalize_order_item(order_id, item_data)

        assert normalized["order_id"] == order_id
        assert normalized["sku"] == "TEST-SKU-001"
        assert normalized["asin"] == "B08N5WRWNW"
        assert normalized["qty"] == 2
        assert normalized["price"] == Decimal("25.99")
        assert normalized["tax"] == Decimal("4.00")
        assert normalized["fee_estimate"] is None

    @patch("src.adapters.amazon.requests.Session")
    def test_get_orders_since_with_mocked_responses(
        self, mock_session, mock_config, mock_orders_response, mock_order_items_response
    ):
        """Test complete order fetching flow with mocked API responses."""
        # Setup mock session
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {
            "x-amzn-RequestId": "test-request-id-123",
            "x-amzn-RateLimit-Limit": "10",
        }

        # Mock different responses for orders and order items endpoints
        def mock_request(method, url, **kwargs):
            mock_response_copy = Mock()
            mock_response_copy.status_code = 200
            mock_response_copy.headers = mock_response.headers

            if "/orders/v0/orders/" in url and "/orderItems" in url:
                # Order items endpoint
                mock_response_copy.json.return_value = mock_order_items_response
            else:
                # Orders endpoint
                mock_response_copy.json.return_value = mock_orders_response

            return mock_response_copy

        mock_session.return_value.request = mock_request

        client = AmazonOrdersClient(mock_config)
        orders, order_items = client.get_orders_since("2023-12-01T00:00:00Z")

        # Verify results
        assert len(orders) == 2
        assert len(order_items) == 2  # One item per order (mocked response reused)

        # Verify first order
        first_order = orders[0]
        assert first_order["order_id"] == "123-4567890-1234567"
        assert first_order["source"] == "amazon"
        assert first_order["total"] == Decimal("29.99")

        # Verify first order item
        first_item = order_items[0]
        assert first_item["order_id"] == "123-4567890-1234567"
        assert first_item["sku"] == "TEST-SKU-001"
        assert first_item["qty"] == 2


class TestAmazonOrdersJob:
    """Test cases for the Amazon orders ETL job."""

    def test_validate_orders_data_valid(self):
        """Test validation with valid orders data."""
        orders = [
            {
                "order_id": "123-4567890-1234567",
                "source": "amazon",
                "purchase_date": datetime.now(UTC),
                "status": "Shipped",
                "customer_id": "buyer@example.com",
                "total": Decimal("29.99"),
                "currency": "EUR",
                "marketplace_id": "A1F83G8C2ARO7P",
            }
        ]

        order_items = [
            {
                "order_id": "123-4567890-1234567",
                "sku": "TEST-SKU-001",
                "asin": "B08N5WRWNW",
                "qty": 2,
                "price": Decimal("25.99"),
                "tax": Decimal("4.00"),
                "fee_estimate": None,
            }
        ]

        # Should not raise any exceptions
        validate_orders_data(orders, order_items)

    def test_validate_orders_data_missing_order_id(self):
        """Test validation fails with missing order_id."""
        orders = [{"source": "amazon", "purchase_date": datetime.now(UTC)}]
        order_items = []

        with pytest.raises(ValueError, match="Order missing order_id"):
            validate_orders_data(orders, order_items)

    def test_validate_orders_data_missing_sku(self):
        """Test validation fails with missing SKU in order item."""
        orders = [
            {
                "order_id": "123-4567890-1234567",
                "source": "amazon",
                "purchase_date": datetime.now(UTC),
            }
        ]

        order_items = [{"order_id": "123-4567890-1234567", "qty": 1}]

        with pytest.raises(ValueError, match="Order item missing sku"):
            validate_orders_data(orders, order_items)

    def test_validate_orders_data_invalid_qty(self):
        """Test validation fails with invalid quantity."""
        orders = [
            {
                "order_id": "123-4567890-1234567",
                "source": "amazon",
                "purchase_date": datetime.now(UTC),
            }
        ]

        order_items = [{"order_id": "123-4567890-1234567", "sku": "TEST-SKU-001", "qty": -1}]

        with pytest.raises(ValueError, match="Order item has invalid qty"):
            validate_orders_data(orders, order_items)

    @patch.dict(os.environ, {"AMZ_SYNC_LOOKBACK_HOURS": "48"})
    def test_get_sync_since_timestamp_custom_lookback(self):
        """Test timestamp calculation with custom lookback period."""
        timestamp = get_sync_since_timestamp()

        # Verify it's a valid ISO timestamp
        assert timestamp.endswith("Z")
        parsed_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert isinstance(parsed_dt, datetime)

    @patch("src.jobs.amazon_orders.AmazonOrdersClient")
    @patch("src.jobs.amazon_orders.upsert_orders")
    @patch("src.jobs.amazon_orders.upsert_order_items")
    @patch("src.jobs.amazon_orders.get_session")
    def test_run_amazon_orders_sync_success(
        self, mock_get_session, mock_upsert_items, mock_upsert_orders, mock_client_class
    ):
        """Test successful Amazon orders sync job execution."""
        # Mock client and its methods
        mock_client = Mock()
        mock_client.get_orders_since.return_value = (
            [  # Mock orders
                {
                    "order_id": "123-4567890-1234567",
                    "source": "amazon",
                    "purchase_date": datetime.now(UTC),
                    "status": "Shipped",
                    "customer_id": "buyer@example.com",
                    "total": Decimal("29.99"),
                    "currency": "EUR",
                    "marketplace_id": "A1F83G8C2ARO7P",
                }
            ],
            [  # Mock order items
                {
                    "order_id": "123-4567890-1234567",
                    "sku": "TEST-SKU-001",
                    "asin": "B08N5WRWNW",
                    "qty": 2,
                    "price": Decimal("25.99"),
                    "tax": Decimal("4.00"),
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
        stats = run_amazon_orders_sync()

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

    @patch("src.jobs.amazon_orders.AmazonOrdersClient")
    def test_run_amazon_orders_sync_no_orders(self, mock_client_class):
        """Test sync job with no orders returned."""
        # Mock client returning empty results
        mock_client = Mock()
        mock_client.get_orders_since.return_value = ([], [])
        mock_client_class.return_value = mock_client

        # Run the sync job
        stats = run_amazon_orders_sync()

        # Verify results
        assert stats["orders_processed"] == 0
        assert stats["orders_inserted"] == 0
        assert stats["orders_updated"] == 0
        assert stats["items_processed"] == 0
        assert stats["items_inserted"] == 0
        assert stats["items_updated"] == 0
