"""
Tests for Shopify Customers ETL job.

Mocks Shopify Admin API responses and validates data normalization and database operations.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

# Import modules under test
from src.adapters.shopify import ShopifyClient, ShopifyConfig
from src.jobs.shopify_customers import (
    normalize_customer_tags,
    run_shopify_customers_sync,
    validate_customers_data,
)


class TestShopifyCustomersJob:
    """Test cases for the Shopify customers ETL job."""

    @pytest.fixture
    def mock_config(self) -> ShopifyConfig:
        """Create a mock Shopify configuration."""
        return ShopifyConfig(shop="test-shop", access_token="shpat_test123", api_version="2024-07")

    @pytest.fixture
    def mock_customers_response(self) -> dict:
        """Mock Shopify customers API response."""
        return {
            "customers": [
                {
                    "id": 123456789,
                    "email": "customer@example.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "created_at": "2023-01-15T08:30:00Z",
                    "updated_at": "2023-12-01T10:45:00Z",
                    "total_spent": "149.95",
                    "orders_count": 3,
                    "state": "enabled",
                    "tags": "VIP,frequent_buyer",
                    "last_order_id": 4755551001,
                    "last_order_name": "#1001",
                },
                {
                    "id": 987654321,
                    "email": "another@example.com",
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "created_at": "2023-06-20T14:20:00Z",
                    "updated_at": "2023-11-15T16:30:00Z",
                    "total_spent": "75.00",
                    "orders_count": 1,
                    "state": "enabled",
                    "tags": "",
                    "last_order_id": 4755551002,
                    "last_order_name": "#1002",
                },
            ]
        }

    @patch("src.adapters.shopify.requests.Session")
    def test_normalize_customer(self, mock_session, mock_config, mock_customers_response):
        """Test customer data normalization."""
        client = ShopifyClient(mock_config)

        customer_data = mock_customers_response["customers"][0]
        normalized = client._normalize_customer(customer_data)

        assert normalized["customer_id"] == "123456789"
        assert normalized["email"] == "customer@example.com"
        assert normalized["first_name"] == "John"
        assert normalized["last_name"] == "Doe"
        assert isinstance(normalized["created_at"], datetime)
        assert isinstance(normalized["updated_at"], datetime)
        assert normalized["total_spent"] == Decimal("149.95")
        assert normalized["orders_count"] == 3
        assert normalized["state"] == "enabled"
        assert normalized["tags"] == ["VIP", "frequent_buyer"]
        assert normalized["last_order_id"] == "4755551001"

    @patch("src.adapters.shopify.requests.Session")
    def test_normalize_customer_empty_tags(
        self, mock_session, mock_config, mock_customers_response
    ):
        """Test customer normalization with empty tags."""
        client = ShopifyClient(mock_config)

        customer_data = mock_customers_response["customers"][1]  # Has empty tags
        normalized = client._normalize_customer(customer_data)

        assert normalized["customer_id"] == "987654321"
        assert normalized["tags"] == []  # Empty string should become empty list

    def test_validate_customers_data_valid(self):
        """Test validation with valid customer data."""
        customers = [
            {
                "customer_id": "123456789",
                "email": "customer@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "total_spent": Decimal("149.95"),
                "orders_count": 3,
                "state": "enabled",
                "tags": ["VIP", "frequent_buyer"],
                "last_order_id": "4755551001",
            }
        ]

        # Should not raise any exceptions
        validate_customers_data(customers)

    def test_validate_customers_data_missing_customer_id(self):
        """Test validation fails with missing customer_id."""
        customers = [
            {
                "email": "customer@example.com",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ]

        with pytest.raises(ValueError, match="Customer missing customer_id"):
            validate_customers_data(customers)

    def test_validate_customers_data_negative_orders_count(self):
        """Test validation fails with negative orders_count."""
        customers = [
            {
                "customer_id": "123456789",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "orders_count": -1,
            }
        ]

        with pytest.raises(ValueError, match="Customer has invalid orders_count"):
            validate_customers_data(customers)

    def test_normalize_customer_tags_list(self):
        """Test tag normalization from list to JSON string."""
        customer = {"customer_id": "123456789", "tags": ["VIP", "frequent_buyer"]}

        normalized = normalize_customer_tags(customer)

        assert normalized["customer_id"] == "123456789"
        assert normalized["tags"] == '["VIP", "frequent_buyer"]'

    def test_normalize_customer_tags_empty_list(self):
        """Test tag normalization with empty list."""
        customer = {"customer_id": "123456789", "tags": []}

        normalized = normalize_customer_tags(customer)

        assert normalized["tags"] is None

    def test_normalize_customer_tags_string(self):
        """Test tag normalization when already a string."""
        customer = {"customer_id": "123456789", "tags": "VIP,frequent_buyer"}

        normalized = normalize_customer_tags(customer)

        assert normalized["tags"] == "VIP,frequent_buyer"

    @patch("src.jobs.shopify_customers.ShopifyClient")
    @patch("src.jobs.shopify_customers.upsert_shopify_customers")
    @patch("src.jobs.shopify_customers.get_session")
    def test_run_shopify_customers_sync_success(
        self, mock_get_session, mock_upsert_customers, mock_client_class
    ):
        """Test successful Shopify customers sync job execution."""
        # Mock client and its methods
        mock_client = Mock()
        mock_customers = [
            {
                "customer_id": "123456789",
                "email": "customer@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "total_spent": Decimal("149.95"),
                "orders_count": 3,
                "state": "enabled",
                "tags": ["VIP", "frequent_buyer"],
                "last_order_id": "4755551001",
                "last_order_date": None,
            }
        ]
        mock_client.get_customers_since.return_value = mock_customers
        mock_client_class.return_value = mock_client

        # Mock database operations
        mock_upsert_customers.return_value = (1, 0)  # 1 inserted, 0 updated

        # Mock session context manager
        mock_session = Mock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Run the sync job
        stats = run_shopify_customers_sync()

        # Verify results
        assert stats["customers_processed"] == 1
        assert stats["customers_inserted"] == 1
        assert stats["customers_updated"] == 0

        # Verify database operations were called
        mock_upsert_customers.assert_called_once()

        # Verify tags were converted to JSON string
        upserted_customers = mock_upsert_customers.call_args[0][0]
        assert len(upserted_customers) == 1
        assert upserted_customers[0]["tags"] == '["VIP", "frequent_buyer"]'

    @patch("src.jobs.shopify_customers.ShopifyClient")
    def test_run_shopify_customers_sync_no_customers(self, mock_client_class):
        """Test sync job with no customers returned."""
        # Mock client returning empty results
        mock_client = Mock()
        mock_client.get_customers_since.return_value = []
        mock_client_class.return_value = mock_client

        # Run the sync job
        stats = run_shopify_customers_sync()

        # Verify results
        assert stats["customers_processed"] == 0
        assert stats["customers_inserted"] == 0
        assert stats["customers_updated"] == 0
