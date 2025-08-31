"""FreeAgent API client adapter with OAuth support for comprehensive read-only data ingestion."""
import logging
import time
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import requests

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None
from requests.exceptions import HTTPError, RequestException
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..utils.oauth import OAuthConfig, OAuthManager, OAuthToken, OAuthTokenError

logger = logging.getLogger(__name__)


class FreeAgentError(Exception):
    """Base exception for FreeAgent API errors."""

    pass


class FreeAgentAuthError(FreeAgentError):
    """Authentication error for FreeAgent API."""

    pass


class FreeAgentRateLimitError(FreeAgentError):
    """Rate limit error for FreeAgent API."""

    pass


class FreeAgentFeatureUnavailableError(FreeAgentError):
    """Feature unavailable error (403/404) for FreeAgent API."""

    pass


class FreeAgentClient:
    """FreeAgent API client with OAuth authentication, rate limiting, and pagination."""

    BASE_URL = "https://api.freeagent.com/v2/"

    def __init__(
        self,
        oauth_config: dict[str, str] | None = None,
        access_token: str | None = None,
        config_path: str = "config/freeagent.yaml"
    ):
        """Initialize FreeAgent client with OAuth or direct token.

        Args:
            oauth_config: OAuth configuration dict with client_id, client_secret, etc.
            access_token: Direct OAuth 2.0 access token (legacy support)
            config_path: Path to FreeAgent configuration file
        """
        self.session = requests.Session()
        self.oauth_manager: OAuthManager | None = None
        self.oauth_token: OAuthToken | None = None
        
        # Set up OAuth if config provided
        if oauth_config and oauth_config.get("client_id") and oauth_config.get("client_secret"):
            oauth_cfg = OAuthConfig(
                client_id=oauth_config["client_id"],
                client_secret=oauth_config["client_secret"],
                redirect_uri=oauth_config.get("redirect_uri", "http://localhost:8000/auth/freeagent/callback"),
                authorization_base_url="https://api.freeagent.com/v2/approve_app",
                token_url="https://api.freeagent.com/v2/token_endpoint",
            )
            self.oauth_manager = OAuthManager(oauth_cfg)
            
            # Set up existing token if available
            if oauth_config.get("access_token"):
                self.oauth_token = OAuthToken(
                    access_token=oauth_config["access_token"],
                    refresh_token=oauth_config.get("refresh_token"),
                )
                self._update_session_auth()
        elif access_token:
            # Legacy direct token support
            self.oauth_token = OAuthToken(access_token=access_token)
            self._update_session_auth()
        else:
            logger.warning("No FreeAgent authentication provided - client will not be functional")

        # Set common headers
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json", 
            "User-Agent": "Stratus-ERP/1.0",
        })

        # Load configuration
        self.config = self._load_config(config_path)
        self.features = self.config.get("features", {})
        self.api_config = self.config.get("api", {})
        self.sync_config = self.config.get("sync", {})

        # Rate limiting
        self.rate_limit_delay = self.api_config.get("rate_limit_delay", 0.5)
        self.last_request_time = 0

        # API versioning support
        api_version = self.api_config.get("api_version")
        if api_version:
            self.session.headers["X-Api-Version"] = api_version
    
    def _update_session_auth(self):
        """Update session authorization header with current token."""
        if self.oauth_token:
            self.session.headers["Authorization"] = self.oauth_token.authorization_header
    
    def get_authorization_url(self, state: str | None = None) -> str:
        """Get OAuth authorization URL for user consent."""
        if not self.oauth_manager:
            raise FreeAgentAuthError("OAuth not configured - need client_id and client_secret")
        return self.oauth_manager.get_authorization_url(state)
    
    def exchange_code_for_token(self, code: str) -> OAuthToken:
        """Exchange authorization code for access token."""
        if not self.oauth_manager:
            raise FreeAgentAuthError("OAuth not configured - need client_id and client_secret")
        
        token = self.oauth_manager.exchange_code_for_token(code)
        self.oauth_token = token
        self._update_session_auth()
        return token
    
    def refresh_access_token(self) -> OAuthToken:
        """Refresh the current access token."""
        if not self.oauth_manager or not self.oauth_token:
            raise FreeAgentAuthError("OAuth not configured or no token available")
        
        token = self.oauth_manager.refresh_token(self.oauth_token)
        self.oauth_token = token
        self._update_session_auth()
        return token
    
    def ensure_valid_token(self):
        """Ensure we have a valid access token, refreshing if necessary."""
        if not self.oauth_token:
            raise FreeAgentAuthError("No access token available")
        
        if self.oauth_token.is_expired and self.oauth_manager:
            logger.info("Token expired, attempting refresh...")
            try:
                self.refresh_access_token()
            except OAuthTokenError as e:
                raise FreeAgentAuthError(f"Failed to refresh token: {e}") from e

    def _load_config(self, config_path: str) -> dict[str, Any]:
        """Load FreeAgent configuration from YAML file."""
        try:
            if yaml is None:
                logger.warning(
                    "PyYAML not installed; skipping FreeAgent config load. Using defaults."
                )
                return {}
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}. Using defaults.")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing config file: {e}")
            return {}

    def _enforce_rate_limit(self):
        """Enforce rate limiting between API requests."""
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            time.sleep(sleep_time)
        # Use the same timestamp to avoid extra time.time() calls (helps tests)
        self.last_request_time = now

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=1, max=10),
        retry=retry_if_exception_type(
            (requests.exceptions.Timeout, requests.exceptions.ConnectionError)
        ),
        reraise=True,
    )
    def _make_request(
        self, method: str, endpoint: str, params: dict | None = None, data: dict | None = None
    ) -> requests.Response:
        """Make authenticated API request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            data: Request body data

        Returns:
            requests.Response object

        Raises:
            FreeAgentAuthError: Authentication failed
            FreeAgentFeatureUnavailableError: Feature not available (403/404)
            FreeAgentRateLimitError: Rate limit exceeded
            FreeAgentError: Other API errors
        """
        # Ensure we have a valid token before making the request
        self.ensure_valid_token()
        
        self._enforce_rate_limit()

        url = urljoin(self.BASE_URL, endpoint)
        timeout = self.api_config.get("timeout", 30)

        try:
            logger.debug(f"Making {method} request to {url}")
            response = self.session.request(
                method=method, url=url, params=params, json=data, timeout=timeout
            )

            # Handle specific HTTP status codes
            if response.status_code == 401:
                raise FreeAgentAuthError("Authentication failed - invalid or expired token")
            elif response.status_code in [403, 404]:
                raise FreeAgentFeatureUnavailableError(
                    f"Feature unavailable (HTTP {response.status_code}): {endpoint}"
                )
            elif response.status_code == 429:
                raise FreeAgentRateLimitError("Rate limit exceeded")
            elif response.status_code >= 400:
                raise FreeAgentError(f"API error (HTTP {response.status_code}): {response.text}")

            response.raise_for_status()
            return response

        except requests.exceptions.Timeout:
            logger.error(f"Request timeout for {url}")
            raise
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error for {url}: {e}")
            raise
        except HTTPError as e:
            logger.error(f"HTTP error for {url}: {e}")
            raise FreeAgentError(f"HTTP error: {e}")
        except RequestException as e:
            logger.error(f"Request exception for {url}: {e}")
            raise FreeAgentError(f"Request error: {e}")

    def _paginate_results(
        self, endpoint: str, params: dict | None = None, data_key: str | None = None
    ) -> list[dict]:
        """Paginate through all results for an endpoint.

        Args:
            endpoint: API endpoint path
            params: Query parameters
            data_key: Key containing the data array in response

        Returns:
            List of all paginated results
        """
        if params is None:
            params = {}

        all_results = []
        page = 1
        max_pages = self.sync_config.get("max_pages", 1000)

        # Default per_page if not specified
        if "per_page" not in params:
            params["per_page"] = self.sync_config.get("batch_size", 100)

        while page <= max_pages:
            params["page"] = page

            try:
                response = self._make_request("GET", endpoint, params=params)
                data = response.json()

                # Determine data key from endpoint if not provided
                if data_key is None:
                    # Extract plural form from endpoint (e.g., "contacts" from "/contacts")
                    endpoint_parts = endpoint.strip("/").split("/")
                    data_key = endpoint_parts[-1] if endpoint_parts else "data"

                # Get results from response
                results = data.get(data_key, [])
                if not results:
                    break

                all_results.extend(results)
                logger.debug(f"Retrieved page {page} with {len(results)} {data_key}")

                # Check if there are more pages
                if len(results) < params["per_page"]:
                    break

                page += 1

            except FreeAgentFeatureUnavailableError as e:
                logger.warning(f"Feature unavailable: {e}")
                raise
            except Exception as e:
                logger.error(f"Error paginating {endpoint} page {page}: {e}")
                raise

        logger.info(f"Retrieved total of {len(all_results)} {data_key} from {endpoint}")
        return all_results

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled in configuration.

        Args:
            feature: Feature name to check

        Returns:
            True if feature is enabled, False otherwise
        """
        return self.features.get(feature, False)

    def get_contacts(self, from_date: str | None = None, to_date: str | None = None) -> list[dict]:
        """Get all contacts with optional date filtering."""
        if not self.is_feature_enabled("contacts"):
            logger.info("Contacts feature is disabled, skipping")
            return []

        params = {}
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date

        try:
            return self._paginate_results("contacts", params, "contacts")
        except FreeAgentFeatureUnavailableError:
            logger.warning("Contacts endpoint unavailable, skipping")
            return []

    def get_invoices(self, from_date: str | None = None, to_date: str | None = None) -> list[dict]:
        """Get all invoices with optional date filtering."""
        if not self.is_feature_enabled("invoices"):
            logger.info("Invoices feature is disabled, skipping")
            return []

        params = {}
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date

        try:
            return self._paginate_results("invoices", params, "invoices")
        except FreeAgentFeatureUnavailableError:
            logger.warning("Invoices endpoint unavailable, skipping")
            return []

    def get_bills(self, from_date: str | None = None, to_date: str | None = None) -> list[dict]:
        """Get all bills with optional date filtering."""
        if not self.is_feature_enabled("bills"):
            logger.info("Bills feature is disabled, skipping")
            return []

        params = {}
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date

        try:
            return self._paginate_results("bills", params, "bills")
        except FreeAgentFeatureUnavailableError:
            logger.warning("Bills endpoint unavailable, skipping")
            return []

    def get_categories(self) -> list[dict]:
        """Get all categories."""
        if not self.is_feature_enabled("categories"):
            logger.info("Categories feature is disabled, skipping")
            return []

        try:
            return self._paginate_results("categories", data_key="categories")
        except FreeAgentFeatureUnavailableError:
            logger.warning("Categories endpoint unavailable, skipping")
            return []

    def get_bank_accounts(self) -> list[dict]:
        """Get all bank accounts."""
        if not self.is_feature_enabled("bank_accounts"):
            logger.info("Bank accounts feature is disabled, skipping")
            return []

        try:
            return self._paginate_results("bank_accounts", data_key="bank_accounts")
        except FreeAgentFeatureUnavailableError:
            logger.warning("Bank accounts endpoint unavailable, skipping")
            return []

    def get_bank_transactions(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        bank_account: str | None = None,
    ) -> list[dict]:
        """Get all bank transactions with optional filtering."""
        if not self.is_feature_enabled("bank_transactions"):
            logger.info("Bank transactions feature is disabled, skipping")
            return []

        params = {}
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date
        if bank_account:
            params["bank_account"] = bank_account

        try:
            return self._paginate_results("bank_transactions", params, "bank_transactions")
        except FreeAgentFeatureUnavailableError:
            logger.warning("Bank transactions endpoint unavailable, skipping")
            return []

    def get_bank_transaction_explanations(
        self, from_date: str | None = None, to_date: str | None = None
    ) -> list[dict]:
        """Get all bank transaction explanations with optional date filtering."""
        if not self.is_feature_enabled("bank_transaction_explanations"):
            logger.info("Bank transaction explanations feature is disabled, skipping")
            return []

        params = {}
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date

        try:
            return self._paginate_results(
                "bank_transaction_explanations", params, "bank_transaction_explanations"
            )
        except FreeAgentFeatureUnavailableError:
            logger.warning("Bank transaction explanations endpoint unavailable, skipping")
            return []

    def get_transactions(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        nominal_code: str | None = None,
    ) -> list[dict]:
        """Get all accounting transactions with optional filtering."""
        if not self.is_feature_enabled("transactions"):
            logger.info("Transactions feature is disabled, skipping")
            return []

        params = {}
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date
        if nominal_code:
            params["nominal_code"] = nominal_code

        try:
            return self._paginate_results("accounting/transactions", params, "transactions")
        except FreeAgentFeatureUnavailableError:
            logger.warning("Transactions endpoint unavailable, skipping")
            return []

    def get_users(self, view: str = "all") -> list[dict]:
        """Get all users with optional view filtering."""
        if not self.is_feature_enabled("users"):
            logger.info("Users feature is disabled, skipping")
            return []

        params = {"view": view}

        try:
            return self._paginate_results("users", params, "users")
        except FreeAgentFeatureUnavailableError:
            logger.warning("Users endpoint unavailable, skipping")
            return []

    def get_changes(self, from_date: str | None = None, to_date: str | None = None) -> list[dict]:
        """Get all changes with optional date filtering."""
        if not self.is_feature_enabled("changes"):
            logger.info("Changes feature is disabled, skipping")
            return []

        params = {}
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date

        try:
            return self._paginate_results("changes", params, "changes")
        except FreeAgentFeatureUnavailableError:
            logger.warning("Changes endpoint unavailable, skipping")
            return []

    def get_default_date_range(self) -> tuple[str, str]:
        """Get default date range for syncing based on configuration."""
        lookback_days = self.sync_config.get("default_lookback_days", 30)
        now = datetime.now()
        to_date = now.strftime("%Y-%m-%d")
        try:
            from_date = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        except Exception:  # defensive when datetime is heavily mocked in tests
            from_date = to_date
        return from_date, to_date


def create_freeagent_client(
    oauth_config: dict[str, str] | None = None,
    access_token: str | None = None,
    config_path: str = "config/freeagent.yaml"
) -> FreeAgentClient:
    """Factory function to create FreeAgent client with OAuth support.

    Args:
        oauth_config: OAuth configuration dict with client_id, client_secret, etc.
        access_token: Direct OAuth 2.0 access token (legacy support)
        config_path: Path to configuration file

    Returns:
        Configured FreeAgentClient instance
    """
    return FreeAgentClient(oauth_config=oauth_config, access_token=access_token, config_path=config_path)
