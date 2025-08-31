"""
Tests for extended ShipBob functionality.

Tests for returns, receiving orders, products, variants, and fulfillment centers.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

# Import modules under test
from src.adapters.shipbob import ShipBobClient, ShipBobConfig
from src.jobs.shipbob_fulfillment_centers import (
    validate_fulfillment_centers_data,
)
from src.jobs.shipbob_products import run_shipbob_products_sync, validate_products_data
from src.jobs.shipbob_receiving import validate_receiving_data
from src.jobs.shipbob_returns import run_shipbob_returns_sync, validate_returns_data


class TestShipBobExtended:
    """Test cases for extended ShipBob functionality."""

    @pytest.fixture
    def mock_config(self) -> ShipBobConfig:
        """Create a mock ShipBob configuration."""
        return ShipBobConfig(
            token="sb_test_token_123", base_url="https://sandbox-api.shipbob.com/2025-07"
        )

    @pytest.fixture
    def mock_returns_response(self) -> list[dict]:
        """Mock ShipBob returns API response."""
        return [
            {
                "id": 12345,
                "reference_id": "shopify-order-001",
                "store_order_id": "order-123",
                "status": "Completed",
                "return_type": "Regular",
                "customer_name": "John Doe",
                "tracking_number": "1Z999AA1234567890",
                "original_shipment_id": 54321,
                "insert_date": "2023-01-15T10:00:00Z",
                "completed_date": "2023-01-20T14:30:00Z",
                "fulfillment_center": {"id": 1, "name": "Cicero (IL)"},
                "inventory": [
                    {
                        "id": 1001,
                        "name": "Test Product",
                        "quantity": 1,
                        "action_requested": {
                            "action": "Restock",
                            "instructions": "Return to inventory",
                        },
                    }
                ],
                "transactions": [{"amount": 2.5, "transaction_type": "ReturnLabelInvoice"}],
            }
        ]

    @pytest.fixture
    def mock_receiving_response(self) -> list[dict]:
        """Mock ShipBob receiving orders API response."""
        return [
            {
                "id": 67890,
                "purchase_order_number": "PO-2023-001",
                "status": "Completed",
                "package_type": "Package",
                "box_packaging_type": "EverythingInOneBox",
                "expected_arrival_date": "2023-01-15T10:00:00Z",
                "insert_date": "2023-01-10T09:00:00Z",
                "last_updated_date": "2023-01-16T14:00:00Z",
                "fulfillment_center": {"id": 1, "name": "Cicero (IL)"},
                "inventory_quantities": [
                    {
                        "inventory_id": 1001,
                        "sku": "PRODUCT-001",
                        "expected_quantity": 100,
                        "received_quantity": 98,
                        "stowed_quantity": 98,
                    }
                ],
                "status_history": [
                    {"status": "Processing", "timestamp": "2023-01-10T09:00:00Z"},
                    {"status": "Completed", "timestamp": "2023-01-16T14:00:00Z"},
                ],
            }
        ]

    @pytest.fixture
    def mock_products_response(self) -> list[dict]:
        """Mock ShipBob products API response."""
        return [
            {
                "id": 1001,
                "name": "Test Product 1",
                "sku": "PRODUCT-001",
                "barcode": "123456789",
                "description": "A test product",
                "category": "Electronics",
                "is_case": False,
                "is_lot": True,
                "variant": {
                    "is_active": True,
                    "is_bundle": False,
                    "is_digital": False,
                    "hazmat": {"is_hazmat": False},
                },
                "dimensions": {"length": 10.5, "width": 8.0, "height": 2.5, "unit": "in"},
                "weight": {"value": 1.2, "unit": "lbs"},
                "value": {"amount": 25.99, "currency": "USD"},
            }
        ]

    @pytest.fixture
    def mock_variants_response(self) -> list[dict]:
        """Mock ShipBob product variants API response."""
        return [
            {
                "id": 2001,
                "name": "Test Product 1 - Large",
                "sku": "PRODUCT-001-L",
                "barcode": "123456789L",
                "is_active": True,
                "dimensions": {"length": 12.0, "width": 10.0, "height": 3.0, "unit": "in"},
                "weight": {"value": 1.5, "unit": "lbs"},
                "value": {"amount": 29.99, "currency": "USD"},
            }
        ]

    @pytest.fixture
    def mock_fulfillment_centers_response(self) -> list[dict]:
        """Mock ShipBob fulfillment centers API response."""
        return [
            {
                "id": 1,
                "name": "Cicero (IL)",
                "address1": "5900 W Ogden Ave",
                "address2": "Suite 100",
                "city": "Cicero",
                "state": "IL",
                "zip_code": "60804",
                "country": "USA",
                "phone_number": "555-555-5555",
                "email": "warehouse@example.com",
                "timezone": "Central Standard Time",
            },
            {
                "id": 2,
                "name": "Las Vegas (NV)",
                "address1": "123 Commerce Blvd",
                "address2": "",
                "city": "Las Vegas",
                "state": "NV",
                "zip_code": "89101",
                "country": "USA",
                "phone_number": "555-555-5556",
                "email": "lv-warehouse@example.com",
                "timezone": "Pacific Standard Time",
            },
        ]

    # Returns Tests
    @patch("src.adapters.shipbob.requests.Session")
    def test_normalize_return(self, mock_session, mock_config, mock_returns_response):
        """Test return data normalization."""
        client = ShipBobClient(mock_config)

        return_data = mock_returns_response[0]
        normalized = client._normalize_return(return_data)

        assert normalized["return_id"] == "12345"
        assert normalized["source"] == "shipbob"
        assert normalized["reference_id"] == "shopify-order-001"
        assert normalized["status"] == "Completed"
        assert normalized["return_type"] == "Regular"
        assert normalized["customer_name"] == "John Doe"
        assert normalized["total_cost"] == Decimal("2.5")
        assert normalized["fulfillment_center_id"] == "1"
        assert len(normalized["items"]) == 1
        assert len(normalized["transactions"]) == 1

    def test_validate_returns_data_valid(self):
        """Test validation with valid returns data."""
        returns_records = [
            {
                "return_id": "12345",
                "source": "shipbob",
                "status": "Completed",
                "items": [{"id": 1, "name": "Test"}],
                "transactions": [{"amount": 2.5}],
                "created_at": datetime.now(UTC),
            }
        ]

        validate_returns_data(returns_records)

        # Check JSON serialization
        assert isinstance(returns_records[0]["items"], str)
        assert isinstance(returns_records[0]["transactions"], str)

    def test_validate_returns_data_missing_id(self):
        """Test validation fails with missing return_id."""
        returns_records = [{"source": "shipbob", "status": "Completed"}]

        with pytest.raises(ValueError, match="Return record missing return_id"):
            validate_returns_data(returns_records)

    # Receiving Orders Tests
    @patch("src.adapters.shipbob.requests.Session")
    def test_normalize_receiving_order(self, mock_session, mock_config, mock_receiving_response):
        """Test receiving order data normalization."""
        client = ShipBobClient(mock_config)

        wro_data = mock_receiving_response[0]
        normalized = client._normalize_receiving_order(wro_data)

        assert normalized["wro_id"] == "67890"
        assert normalized["source"] == "shipbob"
        assert normalized["purchase_order_number"] == "PO-2023-001"
        assert normalized["status"] == "Completed"
        assert normalized["fulfillment_center_id"] == "1"
        assert len(normalized["inventory_quantities"]) == 1
        assert len(normalized["status_history"]) == 2

    def test_validate_receiving_data_valid(self):
        """Test validation with valid receiving data."""
        receiving_records = [
            {
                "wro_id": "67890",
                "source": "shipbob",
                "status": "Completed",
                "inventory_quantities": [{"sku": "TEST-001"}],
                "status_history": [{"status": "Processing"}],
            }
        ]

        validate_receiving_data(receiving_records)

        # Check JSON serialization
        assert isinstance(receiving_records[0]["inventory_quantities"], str)
        assert isinstance(receiving_records[0]["status_history"], str)

    # Products Tests
    @patch("src.adapters.shipbob.requests.Session")
    def test_normalize_shipbob_product(self, mock_session, mock_config, mock_products_response):
        """Test product data normalization."""
        client = ShipBobClient(mock_config)

        product_data = mock_products_response[0]
        normalized = client._normalize_shipbob_product(product_data)

        assert normalized["product_id"] == "1001"
        assert normalized["source"] == "shipbob"
        assert normalized["name"] == "Test Product 1"
        assert normalized["sku"] == "PRODUCT-001"
        assert normalized["category"] == "Electronics"
        assert normalized["is_case"] is False
        assert normalized["is_lot"] is True
        assert normalized["is_active"] is True
        assert normalized["is_hazmat"] is False

    @patch("src.adapters.shipbob.requests.Session")
    def test_normalize_shipbob_variant(self, mock_session, mock_config, mock_variants_response):
        """Test variant data normalization."""
        client = ShipBobClient(mock_config)

        variant_data = mock_variants_response[0]
        normalized = client._normalize_shipbob_variant("1001", variant_data)

        assert normalized["variant_id"] == "2001"
        assert normalized["product_id"] == "1001"
        assert normalized["source"] == "shipbob"
        assert normalized["name"] == "Test Product 1 - Large"
        assert normalized["sku"] == "PRODUCT-001-L"
        assert normalized["is_active"] is True

    def test_validate_products_data_valid(self):
        """Test validation with valid products and variants data."""
        products = [
            {
                "product_id": "1001",
                "source": "shipbob",
                "name": "Test Product",
                "is_active": True,
                "dimensions": {"length": 10, "width": 8},
            }
        ]

        variants = [
            {
                "variant_id": "2001",
                "product_id": "1001",
                "source": "shipbob",
                "name": "Test Variant",
                "is_active": True,
                "dimensions": {"length": 12, "width": 10},
            }
        ]

        validate_products_data(products, variants)

        # Check JSON serialization and boolean conversion
        assert isinstance(products[0]["dimensions"], str)
        assert products[0]["is_active"] == "true"
        assert isinstance(variants[0]["dimensions"], str)
        assert variants[0]["is_active"] == "true"

    def test_validate_products_data_orphaned_variants(self):
        """Test validation filters orphaned variants."""
        products = [{"product_id": "1001", "source": "shipbob"}]

        variants = [
            {"variant_id": "2001", "product_id": "1001", "source": "shipbob"},  # Valid
            {"variant_id": "2002", "product_id": "9999", "source": "shipbob"},  # Orphaned
        ]

        validate_products_data(products, variants)

        # Should filter out orphaned variant
        assert len(variants) == 1
        assert variants[0]["variant_id"] == "2001"

    # Fulfillment Centers Tests
    @patch("src.adapters.shipbob.requests.Session")
    def test_normalize_fulfillment_center(
        self, mock_session, mock_config, mock_fulfillment_centers_response
    ):
        """Test fulfillment center data normalization."""
        client = ShipBobClient(mock_config)

        center_data = mock_fulfillment_centers_response[0]
        normalized = client._normalize_fulfillment_center(center_data)

        assert normalized["center_id"] == "1"
        assert normalized["source"] == "shipbob"
        assert normalized["name"] == "Cicero (IL)"
        assert normalized["city"] == "Cicero"
        assert normalized["state"] == "IL"
        assert normalized["country"] == "USA"
        assert normalized["timezone"] == "Central Standard Time"

    def test_validate_fulfillment_centers_data_valid(self):
        """Test validation with valid fulfillment centers data."""
        centers_records = [
            {"center_id": "1", "source": "shipbob", "name": "Test Center", "city": "Test City"}
        ]

        validate_fulfillment_centers_data(centers_records)

    def test_validate_fulfillment_centers_data_missing_id(self):
        """Test validation fails with missing center_id."""
        centers_records = [{"source": "shipbob", "name": "Test Center"}]

        with pytest.raises(ValueError, match="Fulfillment center missing center_id"):
            validate_fulfillment_centers_data(centers_records)

    # Integration Tests
    @patch("src.jobs.shipbob_returns.ShipBobClient")
    @patch("src.jobs.shipbob_returns.upsert_shipbob_returns")
    @patch("src.jobs.shipbob_returns.get_session")
    def test_run_shipbob_returns_sync_success(
        self, mock_get_session, mock_upsert, mock_client_class
    ):
        """Test successful returns sync job execution."""
        mock_client = Mock()
        mock_client.get_returns.return_value = [
            {
                "return_id": "12345",
                "source": "shipbob",
                "total_cost": Decimal("10.50"),
                "items": [],
                "transactions": [],
            }
        ]
        mock_client_class.return_value = mock_client

        mock_upsert.return_value = (1, 0)
        mock_session = Mock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        stats = run_shipbob_returns_sync()

        assert stats["returns_processed"] == 1
        assert stats["returns_inserted"] == 1
        assert stats["returns_updated"] == 0
        assert stats["total_return_cost"] == 10.5

    @patch("src.jobs.shipbob_products.ShipBobClient")
    @patch("src.jobs.shipbob_products.upsert_shipbob_products")
    @patch("src.jobs.shipbob_products.upsert_shipbob_variants")
    @patch("src.jobs.shipbob_products.get_session")
    def test_run_shipbob_products_sync_success(
        self, mock_get_session, mock_upsert_variants, mock_upsert_products, mock_client_class
    ):
        """Test successful products sync job execution."""
        mock_client = Mock()
        mock_client.get_products.return_value = (
            [{"product_id": "1001", "source": "shipbob", "is_active": True}],
            [{"variant_id": "2001", "product_id": "1001", "source": "shipbob", "is_active": True}],
        )
        mock_client_class.return_value = mock_client

        mock_upsert_products.return_value = (1, 0)
        mock_upsert_variants.return_value = (1, 0)
        mock_session = Mock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        stats = run_shipbob_products_sync()

        assert stats["products_processed"] == 1
        assert stats["products_inserted"] == 1
        assert stats["variants_processed"] == 1
        assert stats["variants_inserted"] == 1
