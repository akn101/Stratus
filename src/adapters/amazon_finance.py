"""
Amazon SP-API Finance/Reports client for Stratus ERP Integration Service.

Handles settlement reports: requesting, polling, downloading, and parsing
Amazon financial settlement data for data warehouse ingestion.
"""

import csv
import io
import logging
import time
from datetime import datetime
from decimal import Decimal
from enum import Enum

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .amazon import AmazonConfig

logger = logging.getLogger(__name__)


class ReportStatus(Enum):
    """Amazon report processing status."""

    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"
    FATAL = "FATAL"


class AmazonRetryableError(Exception):
    """Retryable error for Amazon HTTP calls (429/5xx or transient network errors)."""


class AmazonFinanceClient:
    """Amazon SP-API Finance and Reports client for settlement data."""

    def __init__(self, config: AmazonConfig | None = None):
        self.config = config or AmazonConfig.from_env()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "x-amz-access-token": self.config.access_token,
                "User-Agent": "Stratus-ERP/1.0",
            }
        )

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type(
            (
                AmazonRetryableError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            )
        ),
        reraise=True,
    )
    def _make_request(
        self, method: str, path: str, params: dict | None = None, json_data: dict | None = None
    ) -> dict:
        """
        Make authenticated request to Amazon SP-API with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            params: Query parameters
            json_data: JSON request body

        Returns:
            Response JSON data

        Raises:
            requests.HTTPError: For HTTP errors
            ValueError: For API errors
        """
        url = f"{self.config.endpoint}{path}"

        logger.debug(f"Making {method} request to {url}")

        response = self.session.request(method, url, params=params, json=json_data, timeout=30)

        # Log request tracking (handle mocked responses lacking headers)
        raw_headers = getattr(response, "headers", None)
        headers = raw_headers if isinstance(raw_headers, dict) else {}
        if "x-amzn-RequestId" in headers:
            logger.info(f"Amazon request ID: {headers['x-amzn-RequestId']}")

        if "x-amzn-RateLimit-Limit" in headers:
            logger.debug(f"Rate limit: {headers['x-amzn-RateLimit-Limit']}")

        # Handle rate limiting
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            logger.warning(f"Rate limited, retrying after {retry_after} seconds")
            time.sleep(retry_after)
            raise AmazonRetryableError("Rate limited")

        # Handle server errors
        if 500 <= response.status_code < 600:
            logger.error(f"Server error {response.status_code}: {response.text}")
            raise AmazonRetryableError(f"Server error: {response.status_code}")

        # Handle client errors
        if 400 <= response.status_code < 500:
            logger.error(f"Client error {response.status_code}: {response.text}")
            response.raise_for_status()

        return response.json()

    def request_settlement_report(self, start_iso: str, end_iso: str) -> str:
        """
        Request a settlement report for the given date range.

        Args:
            start_iso: Start date in ISO format (e.g., "2023-01-01T00:00:00Z")
            end_iso: End date in ISO format (e.g., "2023-01-31T23:59:59Z")

        Returns:
            Report ID for tracking the report generation

        Raises:
            requests.HTTPError: For API errors
            ValueError: For invalid response
        """
        logger.info(f"Requesting settlement report from {start_iso} to {end_iso}")

        report_request = {
            "reportType": "GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE",
            "marketplaceIds": self.config.marketplace_ids,
            "dataStartTime": start_iso,
            "dataEndTime": end_iso,
            "reportOptions": {"dateGranularity": "DAY"},
        }

        response_data = self._make_request(
            "POST", "/reports/2021-06-30/reports", json_data=report_request
        )

        report_id = response_data.get("reportId")
        if not report_id:
            raise ValueError(f"No report ID in response: {response_data}")

        logger.info(f"Settlement report requested with ID: {report_id}")
        return report_id

    @retry(
        stop=stop_after_attempt(30),  # Allow longer polling
        wait=wait_exponential(multiplier=2, min=10, max=120),
        retry=retry_if_exception_type((requests.exceptions.RequestException,)),
    )
    def poll_report(self, report_id: str) -> str:
        """
        Poll for report completion and return download URL.

        Args:
            report_id: Report ID from request_settlement_report

        Returns:
            Download URL for the completed report

        Raises:
            requests.HTTPError: For API errors
            ValueError: For report failures or invalid response
        """
        logger.debug(f"Polling report status for {report_id}")

        response_data = self._make_request("GET", f"/reports/2021-06-30/reports/{report_id}")

        processing_status = response_data.get("processingStatus")
        if not processing_status:
            raise ValueError(f"No processing status in response: {response_data}")

        status = ReportStatus(processing_status)
        logger.debug(f"Report {report_id} status: {status.value}")

        if status == ReportStatus.DONE:
            document_id = response_data.get("reportDocumentId")
            if not document_id:
                raise ValueError(f"Report done but no document ID: {response_data}")

            # Get the download URL
            download_url = self._get_document_download_url(document_id)
            logger.info(f"Report {report_id} completed, download URL obtained")
            return download_url

        elif status in [ReportStatus.CANCELLED, ReportStatus.FATAL]:
            raise ValueError(f"Report {report_id} failed with status: {status.value}")

        elif status == ReportStatus.IN_PROGRESS:
            # Raise exception to trigger retry
            raise requests.exceptions.RequestException(f"Report {report_id} still in progress")

        else:
            raise ValueError(f"Unknown report status: {status.value}")

    def _get_document_download_url(self, document_id: str) -> str:
        """
        Get the download URL for a completed report document.

        Args:
            document_id: Document ID from the completed report

        Returns:
            Pre-signed S3 URL for downloading the report
        """
        response_data = self._make_request("GET", f"/reports/2021-06-30/documents/{document_id}")

        download_url = response_data.get("url")
        if not download_url:
            raise ValueError(f"No download URL in document response: {response_data}")

        return download_url

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException,)),
    )
    def download_and_parse_settlement(self, url: str) -> tuple[dict, list[dict]]:
        """
        Download and parse settlement report from the given URL.

        Args:
            url: Pre-signed S3 URL for the settlement report

        Returns:
            Tuple of (settlement_header, settlement_lines)
            - settlement_header: Dict with settlement summary data
            - settlement_lines: List of dicts with individual transaction lines
        """
        logger.info("Downloading settlement report")

        # Download the file
        response = requests.get(url, timeout=300)  # 5 minute timeout
        response.raise_for_status()

        # Parse the CSV content
        csv_content = response.text
        logger.info(f"Downloaded settlement report, size: {len(csv_content)} characters")

        return self._parse_settlement_csv(csv_content)

    def _parse_settlement_csv(self, csv_content: str) -> tuple[dict, list[dict]]:
        """
        Parse the settlement CSV data into normalized format.

        Args:
            csv_content: Raw CSV content from Amazon

        Returns:
            Tuple of (settlement_header, settlement_lines)
        """
        logger.debug("Parsing settlement CSV content")

        csv_reader = csv.DictReader(io.StringIO(csv_content), delimiter="\t")

        settlement_lines = []

        # Track settlement totals
        total_amount = Decimal("0")
        settlement_id = None
        settlement_start = None
        settlement_end = None
        currency = None

        for row in csv_reader:
            # Extract settlement metadata from first row
            if not settlement_id:
                settlement_id = row.get("settlement-id", "").strip()
                settlement_start_str = row.get("settlement-start-date", "").strip()
                settlement_end_str = row.get("settlement-end-date", "").strip()
                currency = row.get("currency", "").strip()

                # Parse dates
                if settlement_start_str:
                    try:
                        settlement_start = datetime.fromisoformat(
                            settlement_start_str.replace("Z", "+00:00")
                        )
                    except ValueError:
                        logger.warning(f"Invalid settlement start date: {settlement_start_str}")

                if settlement_end_str:
                    try:
                        settlement_end = datetime.fromisoformat(
                            settlement_end_str.replace("Z", "+00:00")
                        )
                    except ValueError:
                        logger.warning(f"Invalid settlement end date: {settlement_end_str}")

            # Parse settlement line
            line = self._parse_settlement_line(settlement_id, row)
            if line:
                settlement_lines.append(line)

                # Add to total
                if line.get("amount"):
                    total_amount += line["amount"]

        # Create settlement header
        settlement_header = {
            "settlement_id": settlement_id,
            "period_start": settlement_start,
            "period_end": settlement_end,
            "gross": total_amount,  # Simplified - in practice you'd calculate this properly
            "fees": Decimal("0"),  # Would be calculated from fee lines
            "refunds": Decimal("0"),  # Would be calculated from refund lines
            "net": total_amount,
            "currency": currency,
        }

        logger.info(
            f"Parsed settlement {settlement_id}: {len(settlement_lines)} lines, total: {total_amount} {currency}"
        )

        return settlement_header, settlement_lines

    def _parse_settlement_line(self, settlement_id: str, row: dict[str, str]) -> dict | None:
        """
        Parse a single settlement line from CSV row.

        Args:
            settlement_id: Settlement ID
            row: CSV row as dictionary

        Returns:
            Normalized settlement line dictionary or None if invalid
        """
        try:
            # Parse amount
            amount_str = row.get("amount", "0").strip()
            amount = Decimal(amount_str) if amount_str else Decimal("0")

            # Parse posted date
            posted_date_str = row.get("posted-date", "").strip()
            posted_date = None
            if posted_date_str:
                try:
                    posted_date = datetime.fromisoformat(posted_date_str.replace("Z", "+00:00"))
                except ValueError:
                    logger.warning(f"Invalid posted date: {posted_date_str}")

            return {
                "settlement_id": settlement_id,
                "order_id": row.get("order-id", "").strip() or None,
                "type": row.get("transaction-type", "").strip(),
                "amount": amount,
                "fee_type": row.get("amount-type", "").strip(),
                "posted_date": posted_date,
            }

        except (ValueError, KeyError) as e:
            logger.warning(f"Error parsing settlement line: {e}, row: {row}")
            return None
