"""
Tests for Amazon FBA Inventory ETL job.

Mocks Amazon SP-API inventory responses and validates data normalization and database operations.
"""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from src.adapters.amazon import AmazonConfig

# Import modules under test
from src.adapters.amazon_inventory import AmazonInventoryClient
from src.jobs.amazon_inventory import (
    run_amazon_inventory_incremental_sync,
    run_amazon_inventory_sync,
    validate_inventory_data,
)


class TestAmazonInventoryClient:
    """Test cases for Amazon FBA Inventory client."""

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
    def mock_inventory_response(self) -> dict:
        """Mock Amazon FBA inventory API response."""
        return {
            "payload": {
                "inventorySummaries": [
                    {
                        "asin": "B08N5WRWNW",
                        "sellerSku": "TEST-SKU-001",
                        "fnSku": "X0012345678",
                        "totalQuantity": 50,
                        "fulfillmentCenterDetails": [{"fulfillmentCenterCode": "LTN1"}],
                        "inventoryDetails": {
                            "fulfillableQuantity": 45,
                            "reservedQuantity": {"totalReservedQuantity": 5},
                            "inboundWorkingQuantity": 10,
                        },
                    },
                    {
                        "asin": "B07XYZ12345",
                        "sellerSku": "TEST-SKU-002",
                        "fnSku": "X0098765432",
                        "totalQuantity": 25,
                        "fulfillmentCenterDetails": [{"fulfillmentCenterCode": "MAN2"}],
                        "inventoryDetails": {
                            "fulfillableQuantity": 20,
                            "reservedQuantity": {"totalReservedQuantity": 3},
                            "inboundWorkingQuantity": 2,
                        },
                    },
                    {
                        "asin": "B09ABC67890",
                        "sellerSku": "TEST-SKU-003",
                        "fnSku": "X0055555555",
                        "totalQuantity": 0,
                        "fulfillmentCenterDetails": [{"fulfillmentCenterCode": "LTN1"}],
                        "inventoryDetails": {
                            "fulfillableQuantity": 0,
                            "reservedQuantity": {"totalReservedQuantity": 0},
                            "inboundWorkingQuantity": 15,
                        },
                    },
                ],
                "nextToken": None,
            }
        }

    @pytest.fixture
    def mock_paginated_response_page1(self) -> dict:
        """Mock first page of paginated inventory response."""
        return {
            "payload": {
                "inventorySummaries": [
                    {
                        "asin": "B08N5WRWNW",
                        "sellerSku": "TEST-SKU-001",
                        "fnSku": "X0012345678",
                        "totalQuantity": 50,
                        "fulfillmentCenterDetails": [{"fulfillmentCenterCode": "LTN1"}],
                        "inventoryDetails": {
                            "fulfillableQuantity": 45,
                            "reservedQuantity": {"totalReservedQuantity": 5},
                            "inboundWorkingQuantity": 10,
                        },
                    }
                ],
                "nextToken": "test-next-token-123",
            }
        }

    @pytest.fixture
    def mock_paginated_response_page2(self) -> dict:
        """Mock second page of paginated inventory response."""
        return {
            "payload": {
                "inventorySummaries": [
                    {
                        "asin": "B07XYZ12345",
                        "sellerSku": "TEST-SKU-002",
                        "fnSku": "X0098765432",
                        "totalQuantity": 25,
                        "fulfillmentCenterDetails": [{"fulfillmentCenterCode": "MAN2"}],
                        "inventoryDetails": {
                            "fulfillableQuantity": 20,
                            "reservedQuantity": {"totalReservedQuantity": 3},
                            "inboundWorkingQuantity": 2,
                        },
                    }
                ],
                "nextToken": None,
            }
        }

    @patch("src.adapters.amazon_inventory.requests.Session")
    def test_normalize_inventory_summary(self, mock_session, mock_config):
        """Test inventory data normalization."""
        client = AmazonInventoryClient(mock_config)

        inventory_data = {
            "asin": "B08N5WRWNW",
            "sellerSku": "TEST-SKU-001",
            "fnSku": "X0012345678",
            "totalQuantity": 50,
            "fulfillmentCenterDetails": [{"fulfillmentCenterCode": "LTN1"}],
            "inventoryDetails": {
                "fulfillableQuantity": 45,
                "reservedQuantity": {"totalReservedQuantity": 5},
                "inboundWorkingQuantity": 10,
            },
        }

        normalized = client._normalize_inventory_summary(inventory_data)

        assert normalized["sku"] == "TEST-SKU-001"
        assert normalized["asin"] == "B08N5WRWNW"
        assert normalized["fnsku"] == "X0012345678"
        assert normalized["fc"] == "LTN1"
        assert normalized["on_hand"] == 45
        assert normalized["reserved"] == 5
        assert normalized["inbound"] == 10
        assert isinstance(normalized["updated_at"], datetime)

    @patch("src.adapters.amazon_inventory.requests.Session")
    def test_normalize_inventory_summary_minimal_data(self, mock_session, mock_config):
        """Test normalization with minimal data (no inventory details)."""
        client = AmazonInventoryClient(mock_config)

        inventory_data = {"sellerSku": "MINIMAL-SKU", "totalQuantity": 30}

        normalized = client._normalize_inventory_summary(inventory_data)

        assert normalized["sku"] == "MINIMAL-SKU"
        assert normalized["asin"] is None
        assert normalized["fnsku"] is None
        assert normalized["fc"] is None
        assert normalized["on_hand"] == 30  # Falls back to total quantity
        assert normalized["reserved"] == 0
        assert normalized["inbound"] == 0

    @patch("src.adapters.amazon_inventory.requests.Session")
    def test_normalize_inventory_summary_invalid_data(self, mock_session, mock_config):
        """Test normalization with invalid data."""
        client = AmazonInventoryClient(mock_config)

        # Missing SKU
        invalid_data = {"asin": "B08N5WRWNW", "totalQuantity": 50}

        normalized = client._normalize_inventory_summary(invalid_data)
        assert normalized is None

    @patch("src.adapters.amazon_inventory.requests.Session")
    def test_get_fba_inventory_summaries_single_page(
        self, mock_session, mock_config, mock_inventory_response
    ):
        """Test fetching inventory summaries without pagination."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"x-amzn-RequestId": "test-request-id-123"}
        mock_response.json.return_value = mock_inventory_response
        mock_session.return_value.request.return_value = mock_response

        client = AmazonInventoryClient(mock_config)
        summaries = list(client.get_fba_inventory_summaries())

        assert len(summaries) == 3

        # Verify first item
        first_item = summaries[0]
        assert first_item["sku"] == "TEST-SKU-001"
        assert first_item["on_hand"] == 45
        assert first_item["reserved"] == 5
        assert first_item["inbound"] == 10
        assert first_item["fc"] == "LTN1"

        # Verify third item (zero inventory)
        third_item = summaries[2]
        assert third_item["sku"] == "TEST-SKU-003"
        assert third_item["on_hand"] == 0
        assert third_item["inbound"] == 15

    @patch("src.adapters.amazon_inventory.requests.Session")
    @patch("src.adapters.amazon_inventory.time.sleep")  # Mock sleep to speed up tests
    def test_get_fba_inventory_summaries_pagination(
        self,
        mock_sleep,
        mock_session,
        mock_config,
        mock_paginated_response_page1,
        mock_paginated_response_page2,
    ):
        """Test fetching inventory summaries with pagination."""
        # Mock API responses for pagination
        responses = [mock_paginated_response_page1, mock_paginated_response_page2]
        response_iter = iter(responses)

        def mock_request(method, url, **kwargs):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"x-amzn-RequestId": "test-request-id-123"}
            mock_response.json.return_value = next(response_iter)
            return mock_response

        mock_session.return_value.request.side_effect = mock_request

        client = AmazonInventoryClient(mock_config)
        summaries = list(client.get_fba_inventory_summaries())

        # Should get items from both pages
        assert len(summaries) == 2

        # Verify items from different pages
        assert summaries[0]["sku"] == "TEST-SKU-001"
        assert summaries[1]["sku"] == "TEST-SKU-002"

        # Verify pagination was used (2 API calls)
        assert mock_session.return_value.request.call_count == 2

    @patch("src.adapters.amazon_inventory.requests.Session")
    def test_get_all_inventory_summaries(self, mock_session, mock_config, mock_inventory_response):
        """Test convenience method to get all inventory summaries."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"x-amzn-RequestId": "test-request-id-123"}
        mock_response.json.return_value = mock_inventory_response
        mock_session.return_value.request.return_value = mock_response

        client = AmazonInventoryClient(mock_config)
        all_summaries = client.get_all_inventory_summaries()

        assert len(all_summaries) == 3
        assert all(isinstance(item, dict) for item in all_summaries)
        assert all(item.get("sku") for item in all_summaries)


class TestAmazonInventoryJob:
    """Test cases for the Amazon FBA inventory ETL job."""

    def test_validate_inventory_data_valid(self):
        """Test validation with valid inventory data."""
        inventory_items = [
            {
                "sku": "TEST-SKU-001",
                "asin": "B08N5WRWNW",
                "fnsku": "X0012345678",
                "fc": "LTN1",
                "on_hand": 45,
                "reserved": 5,
                "inbound": 10,
                "updated_at": datetime.now(UTC),
            },
            {
                "sku": "TEST-SKU-002",
                "asin": "B07XYZ12345",
                "fnsku": "X0098765432",
                "fc": "MAN2",
                "on_hand": 20,
                "reserved": 3,
                "inbound": 2,
                "updated_at": datetime.now(UTC),
            },
        ]

        # Should not raise any exceptions
        validate_inventory_data(inventory_items)

    def test_validate_inventory_data_missing_sku(self):
        """Test validation fails with missing SKU."""
        inventory_items = [{"asin": "B08N5WRWNW", "on_hand": 45, "updated_at": datetime.now(UTC)}]

        with pytest.raises(ValueError, match="Inventory item missing SKU"):
            validate_inventory_data(inventory_items)

    def test_validate_inventory_data_invalid_quantity(self):
        """Test validation fails with invalid quantity."""
        inventory_items = [
            {
                "sku": "TEST-SKU-001",
                "on_hand": -5,  # Negative quantity
                "updated_at": datetime.now(UTC),
            }
        ]

        with pytest.raises(ValueError, match="Inventory item has invalid on_hand"):
            validate_inventory_data(inventory_items)

    def test_validate_inventory_data_missing_timestamp(self):
        """Test validation fails with missing timestamp."""
        inventory_items = [
            {
                "sku": "TEST-SKU-001",
                "on_hand": 45,
                # Missing updated_at
            }
        ]

        with pytest.raises(ValueError, match="Inventory item missing updated_at timestamp"):
            validate_inventory_data(inventory_items)

    @patch("src.jobs.amazon_inventory.AmazonInventoryClient")
    @patch("src.jobs.amazon_inventory.upsert_inventory")
    @patch("src.jobs.amazon_inventory.get_session")
    def test_run_amazon_inventory_sync_success(
        self, mock_get_session, mock_upsert_inventory, mock_client_class
    ):
        """Test successful Amazon inventory sync job execution."""
        # Mock client and its methods
        mock_client = Mock()
        mock_inventory_items = [
            {
                "sku": "TEST-SKU-001",
                "asin": "B08N5WRWNW",
                "fnsku": "X0012345678",
                "fc": "LTN1",
                "on_hand": 45,
                "reserved": 5,
                "inbound": 10,
                "updated_at": datetime.now(UTC),
            },
            {
                "sku": "TEST-SKU-002",
                "asin": "B07XYZ12345",
                "fnsku": "X0098765432",
                "fc": "MAN2",
                "on_hand": 20,
                "reserved": 3,
                "inbound": 2,
                "updated_at": datetime.now(UTC),
            },
        ]
        mock_client.get_all_inventory_summaries.return_value = mock_inventory_items
        mock_client_class.return_value = mock_client

        # Mock database operations
        mock_upsert_inventory.return_value = (1, 1)  # 1 inserted, 1 updated

        # Mock session context manager
        mock_session = Mock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Run the sync job
        stats = run_amazon_inventory_sync()

        # Verify results
        assert stats["items_processed"] == 2
        assert stats["items_inserted"] == 1
        assert stats["items_updated"] == 1

        # Verify database operations were called
        mock_upsert_inventory.assert_called_once()
        assert len(mock_upsert_inventory.call_args[0][0]) == 2  # 2 items passed to upsert

    @patch("src.jobs.amazon_inventory.AmazonInventoryClient")
    def test_run_amazon_inventory_sync_no_items(self, mock_client_class):
        """Test sync job with no inventory items returned."""
        # Mock client returning empty results
        mock_client = Mock()
        mock_client.get_all_inventory_summaries.return_value = []
        mock_client_class.return_value = mock_client

        # Run the sync job
        stats = run_amazon_inventory_sync()

        # Verify results
        assert stats["items_processed"] == 0
        assert stats["items_inserted"] == 0
        assert stats["items_updated"] == 0

    @patch("src.jobs.amazon_inventory.AmazonInventoryClient")
    @patch("src.jobs.amazon_inventory.upsert_inventory")
    @patch("src.jobs.amazon_inventory.get_session")
    def test_run_amazon_inventory_sync_aggregation(
        self, mock_get_session, mock_upsert_inventory, mock_client_class
    ):
        """Test inventory sync with SKU aggregation across fulfillment centers."""
        # Mock client with duplicate SKUs from different FCs
        mock_client = Mock()
        mock_inventory_items = [
            {
                "sku": "TEST-SKU-001",
                "fc": "LTN1",
                "on_hand": 25,
                "reserved": 3,
                "inbound": 5,
                "updated_at": datetime.now(UTC),
            },
            {
                "sku": "TEST-SKU-001",  # Same SKU, different FC
                "fc": "MAN2",
                "on_hand": 20,
                "reserved": 2,
                "inbound": 3,
                "updated_at": datetime.now(UTC),
            },
        ]
        mock_client.get_all_inventory_summaries.return_value = mock_inventory_items
        mock_client_class.return_value = mock_client

        # Mock database operations
        mock_upsert_inventory.return_value = (1, 0)

        # Mock session context manager
        mock_session = Mock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Run the sync job
        stats = run_amazon_inventory_sync()

        # Verify aggregation occurred
        assert stats["items_processed"] == 1  # 2 items aggregated into 1

        # Verify aggregated quantities were passed to upsert
        upserted_items = mock_upsert_inventory.call_args[0][0]
        assert len(upserted_items) == 1

        aggregated_item = upserted_items[0]
        assert aggregated_item["sku"] == "TEST-SKU-001"
        assert aggregated_item["on_hand"] == 45  # 25 + 20
        assert aggregated_item["reserved"] == 5  # 3 + 2
        assert aggregated_item["inbound"] == 8  # 5 + 3
        assert aggregated_item["fc"] == "MAN2"  # Last FC wins

    @patch("src.jobs.amazon_inventory.AmazonInventoryClient")
    def test_run_amazon_inventory_incremental_sync(self, mock_client_class):
        """Test incremental sync functionality."""
        # Mock client
        mock_client = Mock()
        mock_inventory_items = [
            {
                "sku": "TEST-SKU-001",
                "on_hand": 45,
                "reserved": 5,
                "inbound": 10,
                "updated_at": datetime.now(UTC),
            },
            {
                "sku": "OTHER-SKU-002",
                "on_hand": 20,
                "reserved": 3,
                "inbound": 2,
                "updated_at": datetime.now(UTC),
            },
        ]
        mock_client.get_all_inventory_summaries.return_value = mock_inventory_items
        mock_client_class.return_value = mock_client

        # Test with specific SKUs
        with patch("src.jobs.amazon_inventory.upsert_inventory") as mock_upsert, patch(
            "src.jobs.amazon_inventory.get_session"
        ) as mock_get_session:
            mock_upsert.return_value = (1, 0)
            mock_session = Mock()
            mock_get_session.return_value.__enter__.return_value = mock_session

            stats = run_amazon_inventory_incremental_sync(["TEST-SKU-001"])

            # Should only process the requested SKU
            assert stats["items_processed"] == 1

            # Verify only the matching SKU was passed to upsert
            upserted_items = mock_upsert.call_args[0][0]
            assert len(upserted_items) == 1
            assert upserted_items[0]["sku"] == "TEST-SKU-001"
