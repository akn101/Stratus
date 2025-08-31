"""
Tests for FreeAgent API adapter.

Tests the FreeAgent client with mocked responses to ensure proper API interaction,
error handling, and feature flag behavior.
"""

from unittest.mock import Mock, patch

import pytest
from requests.exceptions import ConnectionError, Timeout

from src.adapters.freeagent import (
    FreeAgentAuthError,
    FreeAgentClient,
    FreeAgentFeatureUnavailableError,
    FreeAgentRateLimitError,
    create_freeagent_client,
)


@pytest.fixture
def mock_config():
    """Mock FreeAgent configuration."""
    return {
        "features": {
            "contacts": True,
            "invoices": True,
            "bills": True,
            "categories": True,
            "bank_accounts": True,
            "bank_transactions": True,
            "bank_transaction_explanations": True,
            "transactions": True,
            "users": True,
        },
        "api": {
            "max_retries": 3,
            "backoff_factor": 2,
            "timeout": 30,
            "rate_limit_delay": 0.1,  # Faster for tests
            "api_version": "2024-10-01",
        },
        "sync": {
            "default_lookback_days": 30,
            "batch_size": 100,
            "max_pages": 10,  # Smaller for tests
        },
    }


@pytest.fixture
def client(mock_config):
    """Create a FreeAgent client with mocked config."""
    with patch.object(FreeAgentClient, "_load_config", return_value=mock_config):
        return FreeAgentClient(access_token="test_token")


@pytest.fixture
def mock_response():
    """Create a mock HTTP response."""
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"contacts": [{"url": "https://api.freeagent.com/v2/contacts/1"}]}
    response.raise_for_status.return_value = None
    return response


class TestFreeAgentClient:
    """Test FreeAgent client functionality."""

    def test_client_initialization(self, mock_config):
        """Test client initialization with proper configuration."""
        with patch.object(FreeAgentClient, "_load_config", return_value=mock_config):
            client = FreeAgentClient(access_token="test_token")

            assert client.access_token == "test_token"
            assert client.rate_limit_delay == 0.1
            assert client.session.headers["Authorization"] == "Bearer test_token"
            assert client.session.headers["Accept"] == "application/json"
            assert client.session.headers["User-Agent"] == "Stratus-ERP/1.0"
            assert client.session.headers["X-Api-Version"] == "2024-10-01"

    def test_config_loading_missing_file(self):
        """Test graceful handling of missing config file."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            client = FreeAgentClient(access_token="test_token", config_path="missing.yaml")
            assert client.config == {}

    def test_is_feature_enabled(self, client):
        """Test feature flag checking."""
        assert client.is_feature_enabled("contacts") is True
        assert client.is_feature_enabled("disabled_feature") is False

    @patch("time.time")
    def test_rate_limiting(self, mock_time, client):
        """Test rate limiting enforcement."""
        mock_time.side_effect = [1000.0, 1000.1, 1000.2]  # Simulate time progression

        with patch("time.sleep") as mock_sleep:
            client._enforce_rate_limit()
            client._enforce_rate_limit()

            # Should sleep on second call since less than rate_limit_delay passed
            mock_sleep.assert_called_once()


class TestFreeAgentRequests:
    """Test HTTP request handling and error cases."""

    @patch.object(FreeAgentClient, "_load_config", return_value={})
    def test_successful_request(self, mock_config):
        """Test successful API request."""
        client = FreeAgentClient(access_token="test_token")

        with patch.object(client.session, "request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": "test"}
            mock_request.return_value = mock_response

            response = client._make_request("GET", "test")

            assert response.status_code == 200
            mock_request.assert_called_once()

    @patch.object(FreeAgentClient, "_load_config", return_value={})
    def test_authentication_error(self, mock_config):
        """Test 401 authentication error handling."""
        client = FreeAgentClient(access_token="invalid_token")

        with patch.object(client.session, "request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_request.return_value = mock_response

            with pytest.raises(FreeAgentAuthError):
                client._make_request("GET", "test")

    @patch.object(FreeAgentClient, "_load_config", return_value={})
    def test_feature_unavailable_403(self, mock_config):
        """Test 403 feature unavailable error handling."""
        client = FreeAgentClient(access_token="test_token")

        with patch.object(client.session, "request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 403
            mock_request.return_value = mock_response

            with pytest.raises(FreeAgentFeatureUnavailableError):
                client._make_request("GET", "disabled_endpoint")

    @patch.object(FreeAgentClient, "_load_config", return_value={})
    def test_feature_unavailable_404(self, mock_config):
        """Test 404 feature unavailable error handling."""
        client = FreeAgentClient(access_token="test_token")

        with patch.object(client.session, "request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_request.return_value = mock_response

            with pytest.raises(FreeAgentFeatureUnavailableError):
                client._make_request("GET", "missing_endpoint")

    @patch.object(FreeAgentClient, "_load_config", return_value={})
    def test_rate_limit_error(self, mock_config):
        """Test 429 rate limit error handling."""
        client = FreeAgentClient(access_token="test_token")

        with patch.object(client.session, "request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 429
            mock_request.return_value = mock_response

            with pytest.raises(FreeAgentRateLimitError):
                client._make_request("GET", "test")

    @patch.object(FreeAgentClient, "_load_config", return_value={})
    def test_timeout_error(self, mock_config):
        """Test timeout error handling with retry."""
        client = FreeAgentClient(access_token="test_token")

        with patch.object(client.session, "request", side_effect=Timeout("Request timed out")):
            with pytest.raises(Timeout):
                client._make_request("GET", "test")

    @patch.object(FreeAgentClient, "_load_config", return_value={})
    def test_connection_error(self, mock_config):
        """Test connection error handling with retry."""
        client = FreeAgentClient(access_token="test_token")

        with patch.object(
            client.session, "request", side_effect=ConnectionError("Connection failed")
        ):
            with pytest.raises(ConnectionError):
                client._make_request("GET", "test")


class TestFreeAgentPagination:
    """Test pagination functionality."""

    def test_pagination_single_page(self, client):
        """Test pagination with single page response."""
        mock_response_data = {"contacts": [{"url": "https://api.freeagent.com/v2/contacts/1"}]}

        with patch.object(client, "_make_request") as mock_request:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_request.return_value = mock_response

            results = client._paginate_results("contacts", data_key="contacts")

            assert len(results) == 1
            assert results[0]["url"] == "https://api.freeagent.com/v2/contacts/1"
            mock_request.assert_called_once()

    def test_pagination_multiple_pages(self, client):
        """Test pagination with multiple pages."""
        # First page response
        page1_data = {
            "contacts": [
                {"url": f"https://api.freeagent.com/v2/contacts/{i}"} for i in range(1, 101)
            ]
        }
        # Second page response (partial)
        page2_data = {"contacts": [{"url": "https://api.freeagent.com/v2/contacts/101"}]}

        responses = [Mock(), Mock()]
        responses[0].json.return_value = page1_data
        responses[1].json.return_value = page2_data

        with patch.object(client, "_make_request", side_effect=responses) as mock_request:
            results = client._paginate_results("contacts", data_key="contacts")

            assert len(results) == 101
            assert mock_request.call_count == 2

    def test_pagination_empty_response(self, client):
        """Test pagination with empty response."""
        mock_response_data = {"contacts": []}

        with patch.object(client, "_make_request") as mock_request:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_request.return_value = mock_response

            results = client._paginate_results("contacts", data_key="contacts")

            assert len(results) == 0
            mock_request.assert_called_once()


class TestFreeAgentEndpoints:
    """Test individual API endpoints."""

    def test_get_contacts_feature_enabled(self, client):
        """Test get_contacts with feature enabled."""
        mock_data = [{"url": "https://api.freeagent.com/v2/contacts/1", "name": "Test Contact"}]

        with patch.object(client, "_paginate_results", return_value=mock_data) as mock_paginate:
            results = client.get_contacts(from_date="2024-01-01", to_date="2024-01-31")

            assert len(results) == 1
            assert results[0]["name"] == "Test Contact"
            mock_paginate.assert_called_once_with(
                "contacts", {"from_date": "2024-01-01", "to_date": "2024-01-31"}, "contacts"
            )

    def test_get_contacts_feature_disabled(self, client):
        """Test get_contacts with feature disabled."""
        client.features["contacts"] = False

        results = client.get_contacts()

        assert results == []

    def test_get_contacts_feature_unavailable(self, client):
        """Test get_contacts with feature unavailable (403/404)."""
        with patch.object(
            client,
            "_paginate_results",
            side_effect=FreeAgentFeatureUnavailableError("Feature unavailable"),
        ):
            results = client.get_contacts()

            assert results == []

    def test_get_invoices(self, client):
        """Test get_invoices endpoint."""
        mock_data = [{"url": "https://api.freeagent.com/v2/invoices/1", "reference": "INV-001"}]

        with patch.object(client, "_paginate_results", return_value=mock_data) as mock_paginate:
            results = client.get_invoices(from_date="2024-01-01")

            assert len(results) == 1
            mock_paginate.assert_called_once_with(
                "invoices", {"from_date": "2024-01-01"}, "invoices"
            )

    def test_get_categories(self, client):
        """Test get_categories endpoint (no date filtering)."""
        mock_data = [
            {"url": "https://api.freeagent.com/v2/categories/1", "description": "Bank Account"}
        ]

        with patch.object(client, "_paginate_results", return_value=mock_data) as mock_paginate:
            results = client.get_categories()

            assert len(results) == 1
            mock_paginate.assert_called_once_with("categories", data_key="categories")

    def test_get_users_with_view_filter(self, client):
        """Test get_users endpoint with view parameter."""
        mock_data = [{"url": "https://api.freeagent.com/v2/users/1", "email": "test@example.com"}]

        with patch.object(client, "_paginate_results", return_value=mock_data) as mock_paginate:
            results = client.get_users(view="staff")

            assert len(results) == 1
            mock_paginate.assert_called_once_with("users", {"view": "staff"}, "users")

    def test_get_transactions_accounting_endpoint(self, client):
        """Test get_transactions uses accounting/transactions endpoint."""
        mock_data = [{"url": "https://api.freeagent.com/v2/accounting/transactions/1"}]

        with patch.object(client, "_paginate_results", return_value=mock_data) as mock_paginate:
            results = client.get_transactions(nominal_code="750")

            assert len(results) == 1
            mock_paginate.assert_called_once_with(
                "accounting/transactions", {"nominal_code": "750"}, "transactions"
            )


class TestUtilityFunctions:
    """Test utility functions."""

    def test_create_freeagent_client(self):
        """Test factory function."""
        with patch.object(FreeAgentClient, "_load_config", return_value={}):
            client = create_freeagent_client("test_token", "test_config.yaml")

            assert isinstance(client, FreeAgentClient)
            assert client.access_token == "test_token"

    def test_get_default_date_range(self, client):
        """Test default date range calculation."""
        with patch("src.adapters.freeagent.datetime") as mock_datetime:
            mock_now = Mock()
            mock_now.strftime.return_value = "2024-01-31"
            mock_datetime.now.return_value = mock_now
            mock_datetime.timedelta.return_value = Mock()

            # Mock the calculation result
            mock_past = Mock()
            mock_past.strftime.return_value = "2024-01-01"
            with patch("src.adapters.freeagent.datetime.now") as mock_now_func:
                mock_now_func.return_value = mock_now
                mock_now.__sub__.return_value = mock_past

                from_date, to_date = client.get_default_date_range()

                # Should return string dates
                assert isinstance(from_date, str)
                assert isinstance(to_date, str)
