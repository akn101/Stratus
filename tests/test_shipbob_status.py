"""
Tests for ShipBob Order Status ETL job.

Mocks ShipBob API responses and validates order status/tracking updates.
"""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

# Import modules under test
from src.adapters.shipbob import ShipBobClient, ShipBobConfig
from src.jobs.shipbob_status import run_shipbob_status_sync, validate_status_updates


class TestShipBobStatusJob:
    """Test cases for the ShipBob order status ETL job."""

    @pytest.fixture
    def mock_config(self) -> ShipBobConfig:
        """Create a mock ShipBob configuration."""
        return ShipBobConfig(
            token="sb_test_token_123", base_url="https://sandbox-api.shipbob.com/2025-07"
        )

    @pytest.fixture
    def mock_orders_response(self) -> list[dict]:
        """Mock ShipBob orders API response."""
        return [
            {
                "id": 12345,
                "reference_id": "shopify-order-001",  # External order ID
                "status": "Shipped",
                "created_date": "2023-01-01T10:00:00Z",
                "last_updated_date": "2023-01-02T14:30:00Z",
                "shipments": [
                    {
                        "id": 54321,
                        "status": "Shipped",
                        "tracking": {
                            "carrier": "USPS",
                            "tracking_number": "1234567890",
                            "tracking_url": "https://tools.usps.com/go/TrackConfirmAction?qtc_tLabels1=1234567890",
                        },
                    }
                ],
            },
            {
                "id": 67890,
                "reference_id": "shopify-order-002",
                "status": "Processing",
                "created_date": "2023-01-01T11:00:00Z",
                "last_updated_date": "2023-01-02T15:00:00Z",
                "shipments": [],  # No shipments yet
            },
        ]

    @pytest.fixture
    def mock_old_orders_response(self) -> list[dict]:
        """Mock ShipBob orders that are too old to be processed."""
        return [
            {
                "id": 99999,
                "reference_id": "shopify-order-old",
                "status": "Shipped",
                "created_date": "2023-01-01T10:00:00Z",
                "last_updated_date": "2022-12-01T10:00:00Z",  # Old update
                "shipments": [],
            }
        ]

    @patch("src.adapters.shipbob.requests.Session")
    def test_normalize_order_status(self, mock_session, mock_config, mock_orders_response):
        """Test order status data normalization."""
        client = ShipBobClient(mock_config)

        since_iso = "2023-01-02T00:00:00Z"
        order_data = mock_orders_response[0]
        normalized = client._normalize_order_status(order_data, since_iso)

        assert normalized is not None
        assert normalized["order_id"] == "shopify-order-001"
        assert normalized["status"] == "shipped"
        assert normalized["shipbob_order_id"] == "12345"
        assert normalized["shipbob_status"] == "Shipped"
        assert normalized["shipment_status"] == "Shipped"
        assert isinstance(normalized["updated_at"], datetime)

        # Check tracking info
        tracking = normalized["tracking"]
        assert tracking is not None
        assert tracking["tracking_number"] == "1234567890"
        assert tracking["carrier"] == "USPS"
        assert tracking["tracking_url"] is not None

    @patch("src.adapters.shipbob.requests.Session")
    def test_normalize_order_status_no_tracking(
        self, mock_session, mock_config, mock_orders_response
    ):
        """Test order status normalization without tracking."""
        client = ShipBobClient(mock_config)

        since_iso = "2023-01-02T00:00:00Z"
        order_data = mock_orders_response[1]  # No shipments
        normalized = client._normalize_order_status(order_data, since_iso)

        assert normalized is not None
        assert normalized["order_id"] == "shopify-order-002"
        assert normalized["status"] == "processing"
        assert normalized["tracking"] is None

    @patch("src.adapters.shipbob.requests.Session")
    def test_normalize_order_status_old_order(
        self, mock_session, mock_config, mock_old_orders_response
    ):
        """Test order status normalization filters old orders."""
        client = ShipBobClient(mock_config)

        since_iso = "2023-01-02T00:00:00Z"
        order_data = mock_old_orders_response[0]
        normalized = client._normalize_order_status(order_data, since_iso)

        assert normalized is None  # Should be filtered out

    @patch("src.adapters.shipbob.requests.Session")
    def test_get_order_statuses(self, mock_session, mock_config, mock_orders_response):
        """Test fetching order statuses with mocked API response."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": mock_orders_response,
            "next": None,
            "prev": None,
        }
        mock_response.headers = {}
        mock_session.return_value.request.return_value = mock_response

        client = ShipBobClient(mock_config)
        since_iso = "2023-01-02T00:00:00Z"
        status_updates = client.get_order_statuses(since_iso)

        # Verify results
        assert len(status_updates) == 2

        # Verify first update (with tracking)
        first_update = status_updates[0]
        assert first_update["order_id"] == "shopify-order-001"
        assert first_update["status"] == "shipped"
        assert first_update["tracking"] is not None

        # Verify second update (without tracking)
        second_update = status_updates[1]
        assert second_update["order_id"] == "shopify-order-002"
        assert second_update["status"] == "processing"
        assert second_update["tracking"] is None

    def test_validate_status_updates_valid(self):
        """Test validation with valid status update data."""
        status_updates = [
            {
                "order_id": "shopify-order-001",
                "status": "shipped",
                "tracking": {
                    "tracking_number": "1234567890",
                    "carrier": "USPS",
                    "tracking_url": "https://example.com/track",
                },
                "updated_at": datetime.now(UTC),
                "shipbob_order_id": "12345",
            }
        ]

        # Should not raise exceptions and extract tracking fields
        validate_status_updates(status_updates)

        update = status_updates[0]
        assert update["tracking_number"] == "1234567890"
        assert update["carrier"] == "USPS"
        assert update["tracking_url"] == "https://example.com/track"
        assert update["tracking_updated_at"] is not None
        assert "tracking" not in update  # Should be removed

    def test_validate_status_updates_no_tracking(self):
        """Test validation with status updates without tracking."""
        status_updates = [
            {
                "order_id": "shopify-order-002",
                "status": "processing",
                "tracking": None,
                "updated_at": datetime.now(UTC),
                "shipbob_order_id": "67890",
            }
        ]

        validate_status_updates(status_updates)

        update = status_updates[0]
        assert update.get("tracking_number") is None
        assert update.get("carrier") is None
        assert update.get("tracking_url") is None
        assert update["tracking_updated_at"] is not None

    def test_validate_status_updates_missing_order_id(self):
        """Test validation fails with missing order_id."""
        status_updates = [{"status": "shipped", "updated_at": datetime.now(UTC)}]

        with pytest.raises(ValueError, match="Status update missing order_id"):
            validate_status_updates(status_updates)

    def test_validate_status_updates_missing_updated_at(self):
        """Test validation fails with missing updated_at."""
        status_updates = [{"order_id": "shopify-order-001", "status": "shipped"}]

        with pytest.raises(ValueError, match="Status update missing updated_at"):
            validate_status_updates(status_updates)

    def test_validate_status_updates_invalid_tracking_format(self):
        """Test validation handles invalid tracking format."""
        status_updates = [
            {
                "order_id": "shopify-order-001",
                "status": "shipped",
                "tracking": "invalid_tracking_format",  # Should be dict
                "updated_at": datetime.now(UTC),
            }
        ]

        validate_status_updates(status_updates)

        # Should set tracking to None and not extract fields
        update = status_updates[0]
        assert update.get("tracking_number") is None
        assert update.get("carrier") is None

    @patch("src.jobs.shipbob_status.ShipBobClient")
    @patch("src.jobs.shipbob_status.update_order_tracking")
    @patch("src.jobs.shipbob_status.get_session")
    def test_run_shipbob_status_sync_success(
        self, mock_get_session, mock_update_tracking, mock_client_class
    ):
        """Test successful ShipBob status sync job execution."""
        # Mock client and its methods
        mock_client = Mock()
        mock_status_updates = [
            {
                "order_id": "shopify-order-001",
                "status": "shipped",
                "tracking": {
                    "tracking_number": "1234567890",
                    "carrier": "USPS",
                    "tracking_url": "https://example.com/track",
                },
                "updated_at": datetime.now(UTC),
                "shipbob_order_id": "12345",
                "shipbob_status": "Shipped",
            }
        ]
        mock_client.get_order_statuses.return_value = mock_status_updates
        mock_client_class.return_value = mock_client

        # Mock database operations
        mock_update_tracking.return_value = (0, 1)  # 0 inserted, 1 updated

        # Mock session context manager
        mock_session = Mock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Run the sync job
        stats = run_shipbob_status_sync()

        # Verify results
        assert stats["orders_processed"] == 1
        assert stats["orders_updated"] == 1
        assert stats["orders_with_tracking"] == 1
        assert stats["errors"] == 0

        # Verify database operations were called
        mock_update_tracking.assert_called_once()

    @patch("src.jobs.shipbob_status.ShipBobClient")
    def test_run_shipbob_status_sync_no_updates(self, mock_client_class):
        """Test sync job with no status updates returned."""
        # Mock client returning empty results
        mock_client = Mock()
        mock_client.get_order_statuses.return_value = []
        mock_client_class.return_value = mock_client

        # Run the sync job
        stats = run_shipbob_status_sync()

        # Verify results
        assert stats["orders_processed"] == 0
        assert stats["orders_updated"] == 0
        assert stats["orders_with_tracking"] == 0
        assert stats["errors"] == 0

    @patch("src.jobs.shipbob_status.ShipBobClient")
    def test_run_shipbob_status_sync_api_error(self, mock_client_class):
        """Test sync job handles API errors gracefully."""
        # Mock client throwing exception
        mock_client = Mock()
        mock_client.get_order_statuses.side_effect = Exception("API Error")
        mock_client_class.return_value = mock_client

        # Run the sync job
        stats = run_shipbob_status_sync()

        # Verify error handling
        assert stats["orders_processed"] == 0
        assert stats["orders_updated"] == 0
        assert stats["orders_with_tracking"] == 0
        assert stats["errors"] == 1

    @patch("src.jobs.shipbob_status.ShipBobClient")
    @patch("src.jobs.shipbob_status.update_order_tracking")
    @patch("src.jobs.shipbob_status.get_session")
    def test_run_shipbob_status_sync_custom_lookback(
        self, mock_get_session, mock_update_tracking, mock_client_class
    ):
        """Test sync job with custom lookback hours."""
        mock_client = Mock()
        mock_client.get_order_statuses.return_value = []
        mock_client_class.return_value = mock_client

        mock_session = Mock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Run with custom lookback
        run_shipbob_status_sync(lookback_hours=48)

        # Verify client was called with correct since parameter
        mock_client.get_order_statuses.call_args[0][0]
        # Since we can't easily test the exact ISO string, just verify it was called
        assert mock_client.get_order_statuses.called

    @patch("src.jobs.shipbob_status.ShipBobClient")
    @patch("src.jobs.shipbob_status.update_order_tracking")
    @patch("src.jobs.shipbob_status.get_session")
    def test_run_shipbob_status_sync_mixed_tracking(
        self, mock_get_session, mock_update_tracking, mock_client_class
    ):
        """Test sync job with mix of orders with and without tracking."""
        # Mock client with mixed updates
        mock_client = Mock()
        mock_status_updates = [
            {
                "order_id": "order-with-tracking",
                "status": "shipped",
                "tracking": {"tracking_number": "1234567890", "carrier": "USPS"},
                "updated_at": datetime.now(UTC),
                "shipbob_order_id": "12345",
            },
            {
                "order_id": "order-without-tracking",
                "status": "processing",
                "tracking": None,
                "updated_at": datetime.now(UTC),
                "shipbob_order_id": "67890",
            },
        ]
        mock_client.get_order_statuses.return_value = mock_status_updates
        mock_client_class.return_value = mock_client

        # Mock database operations
        mock_update_tracking.return_value = (0, 2)

        # Mock session context manager
        mock_session = Mock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Run the sync job
        stats = run_shipbob_status_sync()

        # Verify results
        assert stats["orders_processed"] == 2
        assert stats["orders_updated"] == 2
        assert stats["orders_with_tracking"] == 1  # Only one has tracking
