"""
Tests for FreeAgent ETL jobs.

Tests the ETL functionality including data transformation, error handling,
and database operations.
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from src.adapters.freeagent import FreeAgentFeatureUnavailableError
from src.jobs.freeagent_categories import run_freeagent_categories_etl, transform_category
from src.jobs.freeagent_contacts import (
    extract_id_from_url,
    run_freeagent_contacts_etl,
    transform_contact,
)
from src.jobs.freeagent_invoices import parse_date, run_freeagent_invoices_etl, transform_invoice


@pytest.fixture
def sample_contact():
    """Sample FreeAgent contact data."""
    return {
        "url": "https://api.freeagent.com/v2/contacts/123",
        "organisation_name": "Test Company Ltd",
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@testcompany.com",
        "phone_number": "+44 20 1234 5678",
        "address1": "123 Test Street",
        "town": "London",
        "country": "United Kingdom",
        "contact_type": "Client",
        "default_payment_terms_in_days": 30,
        "charge_sales_tax": "Auto",
        "account_balance": "1500.50",
        "uses_contact_invoice_sequence": True,
        "status": "Active",
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-16T14:20:00Z",
    }


@pytest.fixture
def sample_invoice():
    """Sample FreeAgent invoice data."""
    return {
        "url": "https://api.freeagent.com/v2/invoices/456",
        "reference": "INV-2024-001",
        "dated_on": "2024-01-15",
        "due_on": "2024-02-14",
        "contact": "https://api.freeagent.com/v2/contacts/123",
        "contact_name": "Test Company Ltd",
        "net_value": "1000.00",
        "sales_tax_value": "200.00",
        "total_value": "1200.00",
        "paid_value": "0.00",
        "due_value": "1200.00",
        "currency": "GBP",
        "exchange_rate": "1.0",
        "status": "Sent",
        "payment_terms_in_days": 30,
        "sales_tax_status": "Standard Rated",
        "outside_of_sales_tax_scope": False,
        "initial_sales_tax_rate": "20.0",
        "comments": "Test invoice",
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-15T10:30:00Z",
    }


@pytest.fixture
def sample_category():
    """Sample FreeAgent category data."""
    return {
        "url": "https://api.freeagent.com/v2/categories/789",
        "description": "Bank Account",
        "nominal_code": "750-1",
        "category_type": "AssetCategory",
        "parent_category": "https://api.freeagent.com/v2/categories/750",
        "auto_sales_tax_rate": "0.0",
        "allowable_for_tax": True,
        "is_visible": True,
        "group_description": "Current Assets",
    }


class TestUtilityFunctions:
    """Test utility functions used across ETL jobs."""

    def test_extract_id_from_url_valid(self):
        """Test extracting ID from valid FreeAgent URL."""
        url = "https://api.freeagent.com/v2/contacts/123"
        assert extract_id_from_url(url) == "123"

    def test_extract_id_from_url_empty(self):
        """Test extracting ID from empty URL."""
        assert extract_id_from_url("") == ""
        assert extract_id_from_url(None) == ""

    def test_extract_id_from_url_invalid(self):
        """Test extracting ID from invalid URL."""
        assert extract_id_from_url("not-a-url") == "not-a-url"
        assert extract_id_from_url("https://api.freeagent.com/v2/") == ""

    def test_parse_date_iso_format(self):
        """Test parsing ISO datetime format."""
        date_str = "2024-01-15T10:30:00Z"
        result = parse_date(date_str)
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_date_simple_format(self):
        """Test parsing simple date format."""
        date_str = "2024-01-15"
        result = parse_date(date_str)
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_date_invalid(self):
        """Test parsing invalid date."""
        assert parse_date("invalid-date") is None
        assert parse_date("") is None
        assert parse_date(None) is None


class TestContactsTransformation:
    """Test contacts data transformation."""

    def test_transform_contact_complete(self, sample_contact):
        """Test transforming complete contact data."""
        result = transform_contact(sample_contact)

        assert result["contact_id"] == "123"
        assert result["source"] == "freeagent"
        assert result["organisation_name"] == "Test Company Ltd"
        assert result["first_name"] == "John"
        assert result["last_name"] == "Doe"
        assert result["email"] == "john@testcompany.com"
        assert result["contact_type"] == "Client"
        assert result["default_payment_terms_in_days"] == 30
        assert result["account_balance"] == "1500.50"
        assert result["uses_contact_invoice_sequence"] == "True"
        assert result["status"] == "Active"

        # Check date parsing
        assert isinstance(result["created_at_api"], datetime)
        assert isinstance(result["updated_at_api"], datetime)

    def test_transform_contact_minimal(self):
        """Test transforming minimal contact data."""
        minimal_contact = {
            "url": "https://api.freeagent.com/v2/contacts/456",
            "organisation_name": "Minimal Company",
        }

        result = transform_contact(minimal_contact)

        assert result["contact_id"] == "456"
        assert result["organisation_name"] == "Minimal Company"
        assert result["first_name"] is None
        assert result["email"] is None
        assert result["created_at_api"] is None

    def test_transform_contact_invalid_dates(self, sample_contact):
        """Test transforming contact with invalid dates."""
        sample_contact["created_at"] = "invalid-date"
        sample_contact["updated_at"] = "2024-13-99T99:99:99Z"  # Invalid date

        result = transform_contact(sample_contact)

        assert result["created_at_api"] is None
        assert result["updated_at_api"] is None


class TestInvoicesTransformation:
    """Test invoices data transformation."""

    def test_transform_invoice_complete(self, sample_invoice):
        """Test transforming complete invoice data."""
        result = transform_invoice(sample_invoice)

        assert result["invoice_id"] == "456"
        assert result["source"] == "freeagent"
        assert result["reference"] == "INV-2024-001"
        assert result["contact_id"] == "123"
        assert result["contact_name"] == "Test Company Ltd"
        assert result["net_value"] == "1000.00"
        assert result["total_value"] == "1200.00"
        assert result["currency"] == "GBP"
        assert result["status"] == "Sent"
        assert result["outside_of_sales_tax_scope"] == "False"

        # Check date parsing
        assert isinstance(result["dated_on"], datetime)
        assert isinstance(result["due_on"], datetime)

    def test_transform_invoice_with_project(self, sample_invoice):
        """Test transforming invoice with project reference."""
        sample_invoice["project"] = "https://api.freeagent.com/v2/projects/999"

        result = transform_invoice(sample_invoice)

        assert result["project_id"] == "999"

    def test_transform_invoice_without_project(self, sample_invoice):
        """Test transforming invoice without project reference."""
        # Remove project field if it exists
        sample_invoice.pop("project", None)

        result = transform_invoice(sample_invoice)

        assert result["project_id"] is None


class TestCategoriesTransformation:
    """Test categories data transformation."""

    def test_transform_category_complete(self, sample_category):
        """Test transforming complete category data."""
        result = transform_category(sample_category)

        assert result["category_id"] == "789"
        assert result["source"] == "freeagent"
        assert result["description"] == "Bank Account"
        assert result["nominal_code"] == "750-1"
        assert result["category_type"] == "AssetCategory"
        assert result["parent_category_id"] == "750"
        assert result["auto_sales_tax_rate"] == "0.0"
        assert result["allowable_for_tax"] == "True"
        assert result["is_visible"] == "True"
        assert result["group_description"] == "Current Assets"

    def test_transform_category_root_level(self, sample_category):
        """Test transforming root level category (no parent)."""
        sample_category.pop("parent_category", None)

        result = transform_category(sample_category)

        assert result["parent_category_id"] is None

    def test_transform_category_boolean_none(self, sample_category):
        """Test transforming category with None boolean values."""
        sample_category["allowable_for_tax"] = None
        sample_category["is_visible"] = None

        result = transform_category(sample_category)

        assert result["allowable_for_tax"] is None
        assert result["is_visible"] is None


class TestETLJobs:
    """Test complete ETL job execution."""

    @patch("src.jobs.freeagent_contacts.create_freeagent_client")
    @patch("src.jobs.freeagent_contacts.upsert_freeagent_contacts")
    def test_contacts_etl_success(self, mock_upsert, mock_create_client, sample_contact):
        """Test successful contacts ETL execution."""
        # Mock client
        mock_client = Mock()
        mock_client.get_contacts.return_value = [sample_contact]
        mock_client.get_default_date_range.return_value = ("2024-01-01", "2024-01-31")
        mock_create_client.return_value = mock_client

        # Mock upsert
        mock_upsert.return_value = (1, 0)  # 1 inserted, 0 updated

        # Run ETL
        result = run_freeagent_contacts_etl("test_token")

        # Verify results
        assert result["inserted"] == 1
        assert result["updated"] == 0
        assert result["total"] == 1

        # Verify calls
        mock_client.get_contacts.assert_called_once()
        mock_upsert.assert_called_once()

    @patch("src.jobs.freeagent_contacts.create_freeagent_client")
    def test_contacts_etl_feature_unavailable(self, mock_create_client):
        """Test contacts ETL with feature unavailable."""
        # Mock client that raises feature unavailable
        mock_client = Mock()
        mock_client.get_contacts.side_effect = FreeAgentFeatureUnavailableError(
            "Feature unavailable"
        )
        mock_create_client.return_value = mock_client

        # Run ETL
        result = run_freeagent_contacts_etl("test_token")

        # Should return zeros with error flag
        assert result["inserted"] == 0
        assert result["updated"] == 0
        assert result["total"] == 0
        assert result["error"] == "feature_unavailable"

    @patch("src.jobs.freeagent_contacts.create_freeagent_client")
    def test_contacts_etl_no_data(self, mock_create_client):
        """Test contacts ETL with no data returned."""
        # Mock client returning empty list
        mock_client = Mock()
        mock_client.get_contacts.return_value = []
        mock_create_client.return_value = mock_client

        # Run ETL
        result = run_freeagent_contacts_etl("test_token")

        # Should return zeros
        assert result["inserted"] == 0
        assert result["updated"] == 0
        assert result["total"] == 0

    @patch("src.jobs.freeagent_contacts.create_freeagent_client")
    @patch("src.jobs.freeagent_contacts.upsert_freeagent_contacts")
    def test_contacts_etl_invalid_data(self, mock_upsert, mock_create_client):
        """Test contacts ETL with invalid data (no contact ID)."""
        # Mock client returning contact without URL
        invalid_contact = {"organisation_name": "Test", "url": ""}
        mock_client = Mock()
        mock_client.get_contacts.return_value = [invalid_contact]
        mock_create_client.return_value = mock_client

        # Run ETL
        result = run_freeagent_contacts_etl("test_token")

        # Should return zeros (no valid contacts)
        assert result["inserted"] == 0
        assert result["updated"] == 0
        assert result["total"] == 0

        # Upsert should not be called
        mock_upsert.assert_not_called()

    @patch("src.jobs.freeagent_invoices.create_freeagent_client")
    @patch("src.jobs.freeagent_invoices.upsert_freeagent_invoices")
    def test_invoices_etl_with_date_range(self, mock_upsert, mock_create_client, sample_invoice):
        """Test invoices ETL with date range parameters."""
        # Mock client
        mock_client = Mock()
        mock_client.get_invoices.return_value = [sample_invoice]
        mock_create_client.return_value = mock_client

        # Mock upsert
        mock_upsert.return_value = (0, 1)  # 0 inserted, 1 updated

        # Run ETL with date range
        result = run_freeagent_invoices_etl(
            "test_token", from_date="2024-01-01", to_date="2024-01-31"
        )

        # Verify results
        assert result["inserted"] == 0
        assert result["updated"] == 1
        assert result["total"] == 1

        # Verify client was called with correct parameters
        mock_client.get_invoices.assert_called_once_with(
            from_date="2024-01-01", to_date="2024-01-31"
        )

    @patch("src.jobs.freeagent_invoices.create_freeagent_client")
    @patch("src.jobs.freeagent_invoices.upsert_freeagent_invoices")
    def test_invoices_etl_full_sync(self, mock_upsert, mock_create_client, sample_invoice):
        """Test invoices ETL with full sync."""
        # Mock client
        mock_client = Mock()
        mock_client.get_invoices.return_value = [sample_invoice]
        mock_create_client.return_value = mock_client

        # Mock upsert
        mock_upsert.return_value = (1, 0)

        # Run ETL with full sync
        run_freeagent_invoices_etl("test_token", full_sync=True)

        # Should call with no date parameters for full sync
        mock_client.get_invoices.assert_called_once_with(from_date=None, to_date=None)

    @patch("src.jobs.freeagent_categories.create_freeagent_client")
    @patch("src.jobs.freeagent_categories.upsert_freeagent_categories")
    def test_categories_etl_success(self, mock_upsert, mock_create_client, sample_category):
        """Test successful categories ETL execution."""
        # Mock client
        mock_client = Mock()
        mock_client.get_categories.return_value = [sample_category]
        mock_create_client.return_value = mock_client

        # Mock upsert
        mock_upsert.return_value = (1, 0)

        # Run ETL
        result = run_freeagent_categories_etl("test_token")

        # Verify results
        assert result["inserted"] == 1
        assert result["updated"] == 0
        assert result["total"] == 1

        # Categories don't use date filters
        mock_client.get_categories.assert_called_once_with()

    @patch("src.jobs.freeagent_contacts.create_freeagent_client")
    def test_contacts_etl_transformation_error(self, mock_create_client):
        """Test contacts ETL with transformation errors."""
        # Mock client returning contact that will cause transformation error
        problematic_contact = {
            "url": "https://api.freeagent.com/v2/contacts/123",
            "created_at": "invalid-date-format-that-will-crash",
        }

        mock_client = Mock()
        mock_client.get_contacts.return_value = [problematic_contact]
        mock_create_client.return_value = mock_client

        with patch(
            "src.jobs.freeagent_contacts.transform_contact",
            side_effect=Exception("Transform error"),
        ):
            # ETL should handle transformation errors gracefully
            result = run_freeagent_contacts_etl("test_token")

            # Should return zeros due to transformation failure
            assert result["inserted"] == 0
            assert result["updated"] == 0
            assert result["total"] == 0
