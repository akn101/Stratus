"""
Tests for Amazon Settlements ETL job.

Mocks Amazon SP-API settlement reports and validates data parsing and database operations.
"""

import os
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from src.adapters.amazon import AmazonConfig

# Import modules under test
from src.adapters.amazon_finance import AmazonFinanceClient
from src.jobs.amazon_settlements import (
    get_settlement_date_range,
    process_single_settlement_report,
    validate_settlement_data,
)


class TestAmazonFinanceClient:
    """Test cases for Amazon Finance/Reports client."""

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
    def mock_settlement_csv(self) -> str:
        """Mock settlement CSV data."""
        return """settlement-id\tsettlement-start-date\tsettlement-end-date\tcurrency\ttransaction-type\torder-id\tamount-type\tamount\tposted-date
12345678901\t2023-12-01T00:00:00Z\t2023-12-07T23:59:59Z\tEUR\tOrder\t123-4567890-1234567\tPrincipal\t25.99\t2023-12-02T10:30:00Z
12345678901\t2023-12-01T00:00:00Z\t2023-12-07T23:59:59Z\tEUR\tOrder\t123-4567890-1234567\tCommission\t-3.90\t2023-12-02T10:30:00Z
12345678901\t2023-12-01T00:00:00Z\t2023-12-07T23:59:59Z\tEUR\tRefund\t987-6543210-9876543\tPrincipal\t-15.50\t2023-12-03T14:15:00Z
12345678901\t2023-12-01T00:00:00Z\t2023-12-07T23:59:59Z\tEUR\tFBAInventoryFee\t\tFBA Fee\t-2.50\t2023-12-04T09:00:00Z"""

    @patch("src.adapters.amazon_finance.requests.Session")
    def test_request_settlement_report(self, mock_session, mock_config):
        """Test settlement report request."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"x-amzn-RequestId": "test-request-id-123"}
        mock_response.json.return_value = {"reportId": "test-report-12345"}
        mock_session.return_value.request.return_value = mock_response

        client = AmazonFinanceClient(mock_config)
        report_id = client.request_settlement_report("2023-12-01T00:00:00Z", "2023-12-07T23:59:59Z")

        assert report_id == "test-report-12345"

        # Verify the request was made correctly
        mock_session.return_value.request.assert_called_once()
        call_args = mock_session.return_value.request.call_args
        assert call_args[0][0] == "POST"  # method
        assert "/reports/2021-06-30/reports" in call_args[0][1]  # path
        assert call_args[1]["json"]["reportType"] == "GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE"

    @patch("src.adapters.amazon_finance.requests.Session")
    def test_poll_report_completed(self, mock_session, mock_config):
        """Test polling for a completed report."""
        # Mock successful responses
        mock_report_response = Mock()
        mock_report_response.status_code = 200
        mock_report_response.json.return_value = {
            "processingStatus": "DONE",
            "reportDocumentId": "test-doc-123",
        }

        mock_doc_response = Mock()
        mock_doc_response.status_code = 200
        mock_doc_response.json.return_value = {
            "url": "https://s3.amazonaws.com/test-bucket/test-report.csv"
        }

        def mock_request(method, url, **kwargs):
            if "documents/" in url:
                return mock_doc_response
            return mock_report_response

        mock_session.return_value.request.side_effect = mock_request

        client = AmazonFinanceClient(mock_config)
        download_url = client.poll_report("test-report-12345")

        assert download_url == "https://s3.amazonaws.com/test-bucket/test-report.csv"

    @patch("src.adapters.amazon_finance.requests.Session")
    def test_poll_report_in_progress(self, mock_session, mock_config):
        """Test polling for a report that's still in progress."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"processingStatus": "IN_PROGRESS"}
        mock_session.return_value.request.return_value = mock_response

        client = AmazonFinanceClient(mock_config)

        # Should raise exception to trigger retry
        with pytest.raises(Exception):
            client.poll_report("test-report-12345")

    @patch("src.adapters.amazon_finance.requests.get")
    def test_download_and_parse_settlement(self, mock_get, mock_config, mock_settlement_csv):
        """Test downloading and parsing settlement data."""
        # Mock successful download
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = mock_settlement_csv
        mock_get.return_value = mock_response

        client = AmazonFinanceClient(mock_config)
        settlement_header, settlement_lines = client.download_and_parse_settlement(
            "https://s3.amazonaws.com/test-bucket/test-report.csv"
        )

        # Verify settlement header
        assert settlement_header["settlement_id"] == "12345678901"
        assert settlement_header["currency"] == "EUR"
        assert isinstance(settlement_header["period_start"], datetime)
        assert isinstance(settlement_header["period_end"], datetime)
        assert isinstance(settlement_header["gross"], Decimal)

        # Verify settlement lines
        assert len(settlement_lines) == 4

        first_line = settlement_lines[0]
        assert first_line["settlement_id"] == "12345678901"
        assert first_line["order_id"] == "123-4567890-1234567"
        assert first_line["type"] == "Order"
        assert first_line["amount"] == Decimal("25.99")
        assert first_line["fee_type"] == "Principal"
        assert isinstance(first_line["posted_date"], datetime)

        # Verify refund line
        refund_line = settlement_lines[2]
        assert refund_line["type"] == "Refund"
        assert refund_line["amount"] == Decimal("-15.50")

        # Verify fee line (no order_id)
        fee_line = settlement_lines[3]
        assert fee_line["type"] == "FBAInventoryFee"
        assert fee_line["order_id"] is None
        assert fee_line["amount"] == Decimal("-2.50")

    def test_parse_settlement_csv_directly(self, mock_config, mock_settlement_csv):
        """Test CSV parsing logic directly."""
        client = AmazonFinanceClient(mock_config)
        settlement_header, settlement_lines = client._parse_settlement_csv(mock_settlement_csv)

        # Detailed assertions
        assert settlement_header["settlement_id"] == "12345678901"
        assert settlement_header["currency"] == "EUR"

        # Verify date parsing
        assert settlement_header["period_start"] == datetime(2023, 12, 1, 0, 0, 0, tzinfo=UTC)
        assert settlement_header["period_end"] == datetime(2023, 12, 7, 23, 59, 59, tzinfo=UTC)

        # Verify all lines parsed correctly
        assert len(settlement_lines) == 4

        # Check line types
        line_types = [line["type"] for line in settlement_lines]
        assert "Order" in line_types
        assert "Refund" in line_types
        assert "FBAInventoryFee" in line_types


class TestAmazonSettlementsJob:
    """Test cases for the Amazon settlements ETL job."""

    def test_validate_settlement_data_valid(self):
        """Test validation with valid settlement data."""
        settlement_header = {
            "settlement_id": "12345678901",
            "period_start": datetime.now(UTC),
            "period_end": datetime.now(UTC),
            "gross": Decimal("100.00"),
            "fees": Decimal("10.00"),
            "refunds": Decimal("5.00"),
            "net": Decimal("85.00"),
            "currency": "EUR",
        }

        settlement_lines = [
            {
                "settlement_id": "12345678901",
                "order_id": "123-4567890-1234567",
                "type": "Order",
                "amount": Decimal("25.99"),
                "fee_type": "Principal",
                "posted_date": datetime.now(UTC),
            },
            {
                "settlement_id": "12345678901",
                "order_id": None,
                "type": "FBAInventoryFee",
                "amount": Decimal("-2.50"),
                "fee_type": "FBA Fee",
                "posted_date": datetime.now(UTC),
            },
        ]

        # Should not raise any exceptions
        validate_settlement_data(settlement_header, settlement_lines)

    def test_validate_settlement_data_missing_settlement_id(self):
        """Test validation fails with missing settlement_id."""
        settlement_header = {"currency": "EUR"}
        settlement_lines = []

        with pytest.raises(ValueError, match="Settlement missing settlement_id"):
            validate_settlement_data(settlement_header, settlement_lines)

    def test_validate_settlement_data_mismatched_settlement_id(self):
        """Test validation fails with mismatched settlement_id in lines."""
        settlement_header = {"settlement_id": "12345678901", "currency": "EUR"}

        settlement_lines = [
            {
                "settlement_id": "99999999999",  # Different ID
                "amount": Decimal("25.99"),
            }
        ]

        with pytest.raises(ValueError, match="Settlement line has mismatched settlement_id"):
            validate_settlement_data(settlement_header, settlement_lines)

    def test_validate_settlement_data_missing_amount(self):
        """Test validation fails with missing amount in line."""
        settlement_header = {"settlement_id": "12345678901", "currency": "EUR"}

        settlement_lines = [
            {
                "settlement_id": "12345678901",
                "type": "Order",
                # Missing amount
            }
        ]

        with pytest.raises(ValueError, match="Settlement line missing amount"):
            validate_settlement_data(settlement_header, settlement_lines)

    @patch.dict(os.environ, {"AMZ_SETTLEMENT_LOOKBACK_DAYS": "30"})
    def test_get_settlement_date_range_custom_lookback(self):
        """Test date range calculation with custom lookback period."""
        start_iso, end_iso = get_settlement_date_range()

        # Verify format
        assert start_iso.endswith("Z")
        assert end_iso.endswith("Z")

        # Parse and verify dates
        start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))

        # Verify the range is approximately 30 days
        delta = end_dt - start_dt
        assert 29 <= delta.days <= 31  # Account for timezone differences

    @patch("src.jobs.amazon_settlements.AmazonFinanceClient")
    @patch("src.jobs.amazon_settlements.upsert_settlements")
    @patch("src.jobs.amazon_settlements.upsert_settlement_lines")
    @patch("src.jobs.amazon_settlements.get_session")
    def test_process_single_settlement_report_success(
        self, mock_get_session, mock_upsert_lines, mock_upsert_settlements, mock_client_class
    ):
        """Test successful processing of a single settlement report."""
        # Mock client and its methods
        mock_client = Mock()
        mock_client.request_settlement_report.return_value = "test-report-12345"
        mock_client.poll_report.return_value = (
            "https://s3.amazonaws.com/test-bucket/test-report.csv"
        )

        mock_settlement_header = {
            "settlement_id": "12345678901",
            "period_start": datetime.now(UTC),
            "period_end": datetime.now(UTC),
            "gross": Decimal("100.00"),
            "fees": Decimal("10.00"),
            "refunds": Decimal("5.00"),
            "net": Decimal("85.00"),
            "currency": "EUR",
        }

        mock_settlement_lines = [
            {
                "settlement_id": "12345678901",
                "order_id": "123-4567890-1234567",
                "type": "Order",
                "amount": Decimal("25.99"),
                "fee_type": "Principal",
                "posted_date": datetime.now(UTC),
            }
        ]

        mock_client.download_and_parse_settlement.return_value = (
            mock_settlement_header,
            mock_settlement_lines,
        )
        mock_client_class.return_value = mock_client

        # Mock database operations
        mock_upsert_settlements.return_value = (1, 0)  # 1 inserted, 0 updated
        mock_upsert_lines.return_value = (1, 0)  # 1 inserted, 0 updated

        # Mock session context manager
        mock_session = Mock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Create config mock
        AmazonConfig(
            access_token="test",
            refresh_token="test",
            client_id="test",
            client_secret="test",
            marketplace_ids=["A1F83G8C2ARO7P"],
        )

        # Process the report
        stats = process_single_settlement_report(
            mock_client, "2023-12-01T00:00:00Z", "2023-12-07T23:59:59Z"
        )

        # Verify results
        assert stats["reports_processed"] == 1
        assert stats["settlements_processed"] == 1
        assert stats["settlements_inserted"] == 1
        assert stats["settlements_updated"] == 0
        assert stats["lines_processed"] == 1
        assert stats["lines_inserted"] == 1
        assert stats["lines_updated"] == 0

        # Verify method calls
        mock_client.request_settlement_report.assert_called_once_with(
            "2023-12-01T00:00:00Z", "2023-12-07T23:59:59Z"
        )
        mock_client.poll_report.assert_called_once_with("test-report-12345")
        mock_client.download_and_parse_settlement.assert_called_once()
        mock_upsert_settlements.assert_called_once()
        mock_upsert_lines.assert_called_once()

    @patch("src.jobs.amazon_settlements.AmazonFinanceClient")
    def test_process_single_settlement_report_no_data(self, mock_client_class):
        """Test processing a report with no settlement data."""
        # Mock client returning empty settlement
        mock_client = Mock()
        mock_client.request_settlement_report.return_value = "test-report-12345"
        mock_client.poll_report.return_value = (
            "https://s3.amazonaws.com/test-bucket/empty-report.csv"
        )
        mock_client.download_and_parse_settlement.return_value = ({}, [])  # Empty data
        mock_client_class.return_value = mock_client

        # Process the report
        stats = process_single_settlement_report(
            mock_client, "2023-12-01T00:00:00Z", "2023-12-07T23:59:59Z"
        )

        # Verify results show no settlements processed
        assert stats["reports_processed"] == 1
        assert stats["settlements_processed"] == 0
        assert stats["settlements_inserted"] == 0
        assert stats["lines_processed"] == 0
