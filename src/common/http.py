"""
Shared HTTP utilities for API client integrations.

Provides common retry patterns, request helpers, and response utilities
used across Amazon, Shopify, ShipBob, and FreeAgent adapters.
"""

import logging
from typing import Any, Dict, Optional, Sequence, Type, Union

import requests
from tenacity import (
    retry,
    retry_if_exception_type, 
    stop_after_attempt,
    wait_exponential
)

logger = logging.getLogger(__name__)


def safe_headers(response: requests.Response) -> Dict[str, str]:
    """
    Safely extract headers from a response object.
    
    Useful for mocked tests where response.headers might not be a proper dict.
    
    Args:
        response: HTTP response object
        
    Returns:
        Dictionary of response headers, empty dict if not accessible
    """
    try:
        headers = getattr(response, "headers", None)
        if isinstance(headers, dict):
            return headers
        elif hasattr(headers, "items"):
            return dict(headers.items())
        else:
            return {}
    except Exception:
        return {}


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    data: Optional[Union[str, bytes, Dict[str, Any]]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 30,
    retry_on: Sequence[Type[Exception]] = (
        requests.exceptions.Timeout, 
        requests.exceptions.ConnectionError
    ),
    backoff: Dict[str, Union[int, float]] = None,
    reraise: bool = True
) -> requests.Response:
    """
    Make HTTP request with configurable retry logic.
    
    Wraps tenacity retry configuration that's repeated across adapters.
    Each adapter can customize retry exceptions and backoff parameters.
    
    Args:
        session: Requests session to use
        method: HTTP method (GET, POST, etc.)
        url: Full URL to request
        params: Query parameters
        json: JSON data for request body
        data: Raw data for request body
        headers: Additional headers (merged with session headers)
        timeout: Request timeout in seconds
        retry_on: Exception types to retry on
        backoff: Backoff configuration dict with keys: multiplier, min, max
        reraise: Whether to reraise exceptions after retry exhaustion
        
    Returns:
        HTTP response object
        
    Raises:
        Various requests exceptions depending on retry configuration
    """
    if backoff is None:
        backoff = {"multiplier": 1, "min": 4, "max": 60}
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(
            multiplier=backoff.get("multiplier", 1),
            min=backoff.get("min", 4),
            max=backoff.get("max", 60)
        ),
        retry=retry_if_exception_type(retry_on),
        reraise=reraise
    )
    def _make_request() -> requests.Response:
        logger.debug(f"Making {method} request to {url}")
        
        # Merge additional headers with session headers
        request_headers = {}
        if headers:
            request_headers.update(headers)
            
        return session.request(
            method=method,
            url=url,
            params=params,
            json=json,
            data=data,
            headers=request_headers if request_headers else None,
            timeout=timeout
        )
    
    return _make_request()