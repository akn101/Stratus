"""
Tests for Shopify Products ETL job.

Mocks Shopify Admin API responses and validates data normalization and database operations.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

# Import modules under test
from src.adapters.shopify import ShopifyClient, ShopifyConfig
from src.jobs.shopify_products import run_shopify_products_sync, validate_products_data


class TestShopifyProductsJob:
    """Test cases for the Shopify products ETL job."""

    @pytest.fixture
    def mock_config(self) -> ShopifyConfig:
        """Create a mock Shopify configuration."""
        return ShopifyConfig(shop="test-shop", access_token="shpat_test123", api_version="2024-07")

    @pytest.fixture
    def mock_products_response(self) -> dict:
        """Mock Shopify products API response."""
        return {
            "products": [
                {
                    "id": 1001,
                    "title": "Test Product 1",
                    "vendor": "Test Vendor",
                    "product_type": "Physical",
                    "created_at": "2023-01-15T08:30:00Z",
                    "updated_at": "2023-12-01T10:45:00Z",
                    "variants": [
                        {
                            "id": 2001,
                            "product_id": 1001,
                            "sku": "TEST-PRODUCT-001",
                            "price": "19.99",
                            "inventory_item_id": 3001,
                            "created_at": "2023-01-15T08:30:00Z",
                            "updated_at": "2023-12-01T10:45:00Z",
                        },
                        {
                            "id": 2002,
                            "product_id": 1001,
                            "sku": "TEST-PRODUCT-001-LARGE",
                            "price": "24.99",
                            "inventory_item_id": 3002,
                            "created_at": "2023-01-15T08:30:00Z",
                            "updated_at": "2023-12-01T10:45:00Z",
                        },
                    ],
                },
                {
                    "id": 1002,
                    "title": "Test Product 2",
                    "vendor": "Another Vendor",
                    "product_type": "Digital",
                    "created_at": "2023-06-20T14:20:00Z",
                    "updated_at": "2023-11-15T16:30:00Z",
                    "variants": [
                        {
                            "id": 2003,
                            "product_id": 1002,
                            "sku": "TEST-PRODUCT-002",
                            "price": "9.99",
                            "inventory_item_id": 3003,
                            "created_at": "2023-06-20T14:20:00Z",
                            "updated_at": "2023-11-15T16:30:00Z",
                        }
                    ],
                },
            ]
        }

    @patch("src.adapters.shopify.requests.Session")
    def test_normalize_product(self, mock_session, mock_config, mock_products_response):
        """Test product data normalization."""
        client = ShopifyClient(mock_config)

        product_data = mock_products_response["products"][0]
        normalized = client._normalize_product(product_data)

        assert normalized["product_id"] == "1001"
        assert normalized["title"] == "Test Product 1"
        assert normalized["vendor"] == "Test Vendor"
        assert normalized["product_type"] == "Physical"
        assert isinstance(normalized["created_at"], datetime)
        assert isinstance(normalized["updated_at"], datetime)

    @patch("src.adapters.shopify.requests.Session")
    def test_normalize_variant(self, mock_session, mock_config, mock_products_response):
        """Test variant data normalization."""
        client = ShopifyClient(mock_config)

        variant_data = mock_products_response["products"][0]["variants"][0]
        normalized = client._normalize_variant("1001", variant_data)

        assert normalized["variant_id"] == "2001"
        assert normalized["product_id"] == "1001"
        assert normalized["sku"] == "TEST-PRODUCT-001"
        assert normalized["price"] == Decimal("19.99")
        assert normalized["inventory_item_id"] == "3001"
        assert isinstance(normalized["created_at"], datetime)
        assert isinstance(normalized["updated_at"], datetime)

    @patch("src.adapters.shopify.requests.Session")
    def test_get_products(self, mock_session, mock_config, mock_products_response):
        """Test fetching products with mocked API response."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_products_response
        mock_session.return_value.request.return_value = mock_response

        client = ShopifyClient(mock_config)
        products, variants = client.get_products()

        # Verify results
        assert len(products) == 2
        assert len(variants) == 3  # 2 variants for first product, 1 for second

        # Verify first product
        first_product = products[0]
        assert first_product["product_id"] == "1001"
        assert first_product["title"] == "Test Product 1"

        # Verify first variant
        first_variant = variants[0]
        assert first_variant["variant_id"] == "2001"
        assert first_variant["product_id"] == "1001"
        assert first_variant["sku"] == "TEST-PRODUCT-001"

    def test_validate_products_data_valid(self):
        """Test validation with valid product data."""
        products = [
            {
                "product_id": "1001",
                "title": "Test Product 1",
                "vendor": "Test Vendor",
                "product_type": "Physical",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ]

        variants = [
            {
                "variant_id": "2001",
                "product_id": "1001",
                "sku": "TEST-PRODUCT-001",
                "price": Decimal("19.99"),
                "inventory_item_id": "3001",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ]

        # Should not raise any exceptions
        validate_products_data(products, variants)

    def test_validate_products_data_missing_product_id(self):
        """Test validation fails with missing product_id."""
        products = [
            {
                "title": "Test Product 1",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ]
        variants = []

        with pytest.raises(ValueError, match="Product missing product_id"):
            validate_products_data(products, variants)

    def test_validate_products_data_missing_variant_id(self):
        """Test validation fails with missing variant_id."""
        products = [
            {
                "product_id": "1001",
                "title": "Test Product 1",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ]

        variants = [
            {
                "product_id": "1001",
                "sku": "TEST-PRODUCT-001",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ]

        with pytest.raises(ValueError, match="Variant missing variant_id"):
            validate_products_data(products, variants)

    def test_validate_products_data_orphaned_variants(self):
        """Test validation with orphaned variants (warns but doesn't fail)."""
        products = [
            {
                "product_id": "1001",
                "title": "Test Product 1",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ]

        variants = [
            {
                "variant_id": "2001",
                "product_id": "1001",  # Valid product_id
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
            {
                "variant_id": "2002",
                "product_id": "9999",  # Invalid product_id (orphaned)
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        ]

        # Should not raise exception but will log warning
        validate_products_data(products, variants)

    @patch("src.jobs.shopify_products.ShopifyClient")
    @patch("src.jobs.shopify_products.upsert_shopify_products")
    @patch("src.jobs.shopify_products.upsert_shopify_variants")
    @patch("src.jobs.shopify_products.get_session")
    def test_run_shopify_products_sync_success(
        self, mock_get_session, mock_upsert_variants, mock_upsert_products, mock_client_class
    ):
        """Test successful Shopify products sync job execution."""
        # Mock client and its methods
        mock_client = Mock()
        mock_products = [
            {
                "product_id": "1001",
                "title": "Test Product 1",
                "vendor": "Test Vendor",
                "product_type": "Physical",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ]

        mock_variants = [
            {
                "variant_id": "2001",
                "product_id": "1001",
                "sku": "TEST-PRODUCT-001",
                "price": Decimal("19.99"),
                "inventory_item_id": "3001",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ]

        mock_client.get_products.return_value = (mock_products, mock_variants)
        mock_client_class.return_value = mock_client

        # Mock database operations
        mock_upsert_products.return_value = (1, 0)  # 1 inserted, 0 updated
        mock_upsert_variants.return_value = (1, 0)  # 1 inserted, 0 updated

        # Mock session context manager
        mock_session = Mock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Run the sync job
        stats = run_shopify_products_sync()

        # Verify results
        assert stats["products_processed"] == 1
        assert stats["products_inserted"] == 1
        assert stats["products_updated"] == 0
        assert stats["variants_processed"] == 1
        assert stats["variants_inserted"] == 1
        assert stats["variants_updated"] == 0

        # Verify database operations were called
        mock_upsert_products.assert_called_once()
        mock_upsert_variants.assert_called_once()

    @patch("src.jobs.shopify_products.ShopifyClient")
    def test_run_shopify_products_sync_no_products(self, mock_client_class):
        """Test sync job with no products returned."""
        # Mock client returning empty results
        mock_client = Mock()
        mock_client.get_products.return_value = ([], [])
        mock_client_class.return_value = mock_client

        # Run the sync job
        stats = run_shopify_products_sync()

        # Verify results
        assert stats["products_processed"] == 0
        assert stats["products_inserted"] == 0
        assert stats["products_updated"] == 0
        assert stats["variants_processed"] == 0
        assert stats["variants_inserted"] == 0
        assert stats["variants_updated"] == 0

    @patch("src.jobs.shopify_products.ShopifyClient")
    @patch("src.jobs.shopify_products.upsert_shopify_products")
    @patch("src.jobs.shopify_products.upsert_shopify_variants")
    @patch("src.jobs.shopify_products.get_session")
    def test_run_shopify_products_sync_filters_orphaned_variants(
        self, mock_get_session, mock_upsert_variants, mock_upsert_products, mock_client_class
    ):
        """Test sync job filters out orphaned variants."""
        # Mock client with orphaned variant
        mock_client = Mock()
        mock_products = [
            {
                "product_id": "1001",
                "title": "Test Product 1",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ]

        mock_variants = [
            {
                "variant_id": "2001",
                "product_id": "1001",  # Valid
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
            {
                "variant_id": "2002",
                "product_id": "9999",  # Invalid (orphaned)
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        ]

        mock_client.get_products.return_value = (mock_products, mock_variants)
        mock_client_class.return_value = mock_client

        # Mock database operations
        mock_upsert_products.return_value = (1, 0)
        mock_upsert_variants.return_value = (1, 0)  # Should only process 1 variant

        # Mock session context manager
        mock_session = Mock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Run the sync job
        stats = run_shopify_products_sync()

        # Verify orphaned variant was filtered out
        assert stats["products_processed"] == 1
        assert stats["variants_processed"] == 1  # Only 1 variant processed, not 2

        # Verify only valid variant was passed to upsert
        upserted_variants = mock_upsert_variants.call_args[0][0]
        assert len(upserted_variants) == 1
        assert upserted_variants[0]["variant_id"] == "2001"
