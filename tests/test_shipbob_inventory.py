"""
Tests for ShipBob Inventory ETL job.

Mocks ShipBob API responses and validates data normalization and database operations.
"""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

# Import modules under test
from src.adapters.shipbob import ShipBobClient, ShipBobConfig
from src.jobs.shipbob_inventory import run_shipbob_inventory_sync, validate_inventory_data


class TestShipBobInventoryJob:
    """Test cases for the ShipBob inventory ETL job."""

    @pytest.fixture
    def mock_config(self) -> ShipBobConfig:
        """Create a mock ShipBob configuration."""
        return ShipBobConfig(
            token="sb_test_token_123", base_url="https://sandbox-api.shipbob.com/2025-07"
        )

    @pytest.fixture
    def mock_inventory_response(self) -> list[dict]:
        """Mock ShipBob inventory level API response."""
        return [
            {
                "inventory_id": 12345,
                "sku": "PRODUCT-001",
                "name": "Test Product 1",
                "total_on_hand_quantity": 100,
                "total_sellable_quantity": 95,
                "total_fulfillable_quantity": 90,
                "total_committed_quantity": 5,
                "total_awaiting_quantity": 10,
                "total_backordered_quantity": 0,
                "total_exception_quantity": 0,
                "total_internal_transfer_quantity": 0,
            },
            {
                "inventory_id": 67890,
                "sku": "PRODUCT-002",
                "name": "Test Product 2",
                "total_on_hand_quantity": 50,
                "total_sellable_quantity": 48,
                "total_fulfillable_quantity": 45,
                "total_committed_quantity": 2,
                "total_awaiting_quantity": 0,
                "total_backordered_quantity": 5,
                "total_exception_quantity": 1,
                "total_internal_transfer_quantity": 0,
            },
        ]

    @patch("src.adapters.shipbob.requests.Session")
    def test_normalize_inventory_item(self, mock_session, mock_config, mock_inventory_response):
        """Test inventory item data normalization."""
        client = ShipBobClient(mock_config)

        item_data = mock_inventory_response[0]
        normalized = client._normalize_inventory_item(item_data)

        assert normalized["sku"] == "PRODUCT-001"
        assert normalized["source"] == "shipbob"
        assert normalized["quantity_on_hand"] == 100
        assert normalized["quantity_available"] == 95
        assert normalized["quantity_reserved"] == 5
        assert normalized["quantity_incoming"] == 10
        assert normalized["fulfillable_quantity"] == 90
        assert normalized["backordered_quantity"] == 0
        assert normalized["exception_quantity"] == 0
        assert normalized["internal_transfer_quantity"] == 0
        assert normalized["inventory_name"] == "Test Product 1"
        assert normalized["inventory_id"] == "12345"
        assert isinstance(normalized["last_updated"], datetime)

    @patch("src.adapters.shipbob.requests.Session")
    def test_get_inventory(self, mock_session, mock_config, mock_inventory_response):
        """Test fetching inventory with mocked API response."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": mock_inventory_response,
            "next": None,
            "prev": None,
        }
        mock_response.headers = {}
        mock_session.return_value.request.return_value = mock_response

        client = ShipBobClient(mock_config)
        inventory_items = client.get_inventory()

        # Verify results
        assert len(inventory_items) == 2

        # Verify first item
        first_item = inventory_items[0]
        assert first_item["sku"] == "PRODUCT-001"
        assert first_item["source"] == "shipbob"
        assert first_item["quantity_on_hand"] == 100
        assert first_item["quantity_available"] == 95

        # Verify second item
        second_item = inventory_items[1]
        assert second_item["sku"] == "PRODUCT-002"
        assert second_item["quantity_on_hand"] == 50
        assert second_item["backordered_quantity"] == 5

    def test_validate_inventory_data_valid(self):
        """Test validation with valid inventory data."""
        inventory_records = [
            {
                "sku": "PRODUCT-001",
                "source": "shipbob",
                "quantity_on_hand": 100,
                "quantity_available": 95,
                "quantity_reserved": 5,
                "quantity_incoming": 10,
                "fulfillable_quantity": 90,
                "backordered_quantity": 0,
                "exception_quantity": 0,
                "internal_transfer_quantity": 0,
                "inventory_name": "Test Product",
                "inventory_id": "12345",
                "last_updated": datetime.now(UTC),
            }
        ]

        # Should not raise any exceptions
        validate_inventory_data(inventory_records)

    def test_validate_inventory_data_missing_sku(self):
        """Test validation fails with missing SKU."""
        inventory_records = [
            {"source": "shipbob", "quantity_on_hand": 100, "last_updated": datetime.now(UTC)}
        ]

        with pytest.raises(ValueError, match="Inventory record missing SKU"):
            validate_inventory_data(inventory_records)

    def test_validate_inventory_data_missing_source(self):
        """Test validation fails with missing source."""
        inventory_records = [
            {"sku": "PRODUCT-001", "quantity_on_hand": 100, "last_updated": datetime.now(UTC)}
        ]

        with pytest.raises(ValueError, match="Inventory record missing source"):
            validate_inventory_data(inventory_records)

    def test_validate_inventory_data_numeric_conversion(self):
        """Test validation converts string numbers to integers."""
        inventory_records = [
            {
                "sku": "PRODUCT-001",
                "source": "shipbob",
                "quantity_on_hand": "100",  # String number
                "quantity_available": "95.0",  # Float string
                "quantity_reserved": None,  # None value
                "last_updated": datetime.now(UTC),
            }
        ]

        validate_inventory_data(inventory_records)

        assert inventory_records[0]["quantity_on_hand"] == 100
        assert inventory_records[0]["quantity_available"] == 95
        assert inventory_records[0]["quantity_reserved"] is None

    @patch("src.jobs.shipbob_inventory.ShipBobClient")
    @patch("src.jobs.shipbob_inventory.upsert_inventory")
    @patch("src.jobs.shipbob_inventory.get_session")
    def test_run_shipbob_inventory_sync_success(
        self, mock_get_session, mock_upsert_inventory, mock_client_class
    ):
        """Test successful ShipBob inventory sync job execution."""
        # Mock client and its methods
        mock_client = Mock()
        mock_inventory = [
            {
                "sku": "PRODUCT-001",
                "source": "shipbob",
                "quantity_on_hand": 100,
                "quantity_available": 95,
                "quantity_reserved": 5,
                "quantity_incoming": 10,
                "fulfillable_quantity": 90,
                "backordered_quantity": 0,
                "exception_quantity": 0,
                "internal_transfer_quantity": 0,
                "inventory_name": "Test Product",
                "inventory_id": "12345",
                "last_updated": datetime.now(UTC),
            }
        ]
        mock_client.get_inventory.return_value = mock_inventory
        mock_client_class.return_value = mock_client

        # Mock database operations
        mock_upsert_inventory.return_value = (1, 0)  # 1 inserted, 0 updated

        # Mock session context manager
        mock_session = Mock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Run the sync job
        stats = run_shipbob_inventory_sync()

        # Verify results
        assert stats["inventory_processed"] == 1
        assert stats["inventory_inserted"] == 1
        assert stats["inventory_updated"] == 0
        assert stats["errors"] == 0

        # Verify database operations were called
        mock_upsert_inventory.assert_called_once()

    @patch("src.jobs.shipbob_inventory.ShipBobClient")
    def test_run_shipbob_inventory_sync_no_inventory(self, mock_client_class):
        """Test sync job with no inventory returned."""
        # Mock client returning empty results
        mock_client = Mock()
        mock_client.get_inventory.return_value = []
        mock_client_class.return_value = mock_client

        # Run the sync job
        stats = run_shipbob_inventory_sync()

        # Verify results
        assert stats["inventory_processed"] == 0
        assert stats["inventory_inserted"] == 0
        assert stats["inventory_updated"] == 0
        assert stats["errors"] == 0

    @patch("src.jobs.shipbob_inventory.ShipBobClient")
    def test_run_shipbob_inventory_sync_api_error(self, mock_client_class):
        """Test sync job handles API errors gracefully."""
        # Mock client throwing exception
        mock_client = Mock()
        mock_client.get_inventory.side_effect = Exception("API Error")
        mock_client_class.return_value = mock_client

        # Run the sync job
        stats = run_shipbob_inventory_sync()

        # Verify error handling
        assert stats["inventory_processed"] == 0
        assert stats["inventory_inserted"] == 0
        assert stats["inventory_updated"] == 0
        assert stats["errors"] == 1

    @patch("src.jobs.shipbob_inventory.ShipBobClient")
    @patch("src.jobs.shipbob_inventory.upsert_inventory")
    @patch("src.jobs.shipbob_inventory.get_session")
    def test_run_shipbob_inventory_sync_filters_empty_skus(
        self, mock_get_session, mock_upsert_inventory, mock_client_class
    ):
        """Test sync job filters out items with empty SKUs."""
        # Mock client with empty SKU
        mock_client = Mock()
        mock_inventory = [
            {
                "sku": "PRODUCT-001",  # Valid
                "source": "shipbob",
                "quantity_on_hand": 100,
                "last_updated": datetime.now(UTC),
            },
            {
                "sku": "",  # Invalid (empty)
                "source": "shipbob",
                "quantity_on_hand": 50,
                "last_updated": datetime.now(UTC),
            },
        ]
        mock_client.get_inventory.return_value = mock_inventory
        mock_client_class.return_value = mock_client

        # Mock database operations
        mock_upsert_inventory.return_value = (1, 0)

        # Mock session context manager
        mock_session = Mock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Run the sync job
        stats = run_shipbob_inventory_sync()

        # Verify only valid item was processed
        assert stats["inventory_processed"] == 1  # Only 1 valid item should be processed

        # Verify only valid inventory was passed to upsert
        upserted_inventory = mock_upsert_inventory.call_args[0][0]
        assert len(upserted_inventory) == 1
        assert upserted_inventory[0]["sku"] == "PRODUCT-001"
