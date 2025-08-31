"""
Rate limiting utilities for API integrations.

Provides helpers to parse rate limit headers, calculate sleep times,
and implement intelligent rate limiting strategies.
"""

import logging
import time

from requests import Response

logger = logging.getLogger(__name__)


class RateLimitInfo:
    """Container for rate limit information from API response headers."""

    def __init__(
        self,
        limit: int | None = None,
        remaining: int | None = None,
        reset_time: float | None = None,
        retry_after: float | None = None,
        current_usage: float | None = None,
    ):
        self.limit = limit
        self.remaining = remaining
        self.reset_time = reset_time
        self.retry_after = retry_after
        self.current_usage = current_usage

    @property
    def usage_ratio(self) -> float | None:
        """Calculate current usage as ratio (0.0 to 1.0)."""
        if self.limit is None or self.remaining is None:
            return self.current_usage

        if self.limit == 0:
            return 1.0

        used = self.limit - self.remaining
        return used / self.limit

    @property
    def is_near_limit(self, threshold: float = 0.8) -> bool:
        """Check if current usage is near the rate limit."""
        ratio = self.usage_ratio
        if ratio is None:
            return False
        return ratio >= threshold

    def __repr__(self) -> str:
        return (
            f"RateLimitInfo(limit={self.limit}, remaining={self.remaining}, "
            f"usage={self.usage_ratio:.2%})"
        )


def parse_shopify_rate_limit(response: Response) -> RateLimitInfo:
    """
    Parse Shopify rate limit headers.

    Shopify uses: X-Shopify-Shop-Api-Call-Limit: 32/40
    """
    header = response.headers.get("X-Shopify-Shop-Api-Call-Limit")
    if not header:
        return RateLimitInfo()

    try:
        used_str, limit_str = header.split("/")
        used = int(used_str)
        limit = int(limit_str)
        remaining = limit - used

        return RateLimitInfo(limit=limit, remaining=remaining)
    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to parse Shopify rate limit header '{header}': {e}")
        return RateLimitInfo()


def parse_generic_rate_limit(response: Response) -> RateLimitInfo:
    """
    Parse generic rate limit headers (GitHub/Twitter style).

    Headers:
    - X-RateLimit-Limit
    - X-RateLimit-Remaining
    - X-RateLimit-Reset
    - Retry-After
    """
    limit = None
    remaining = None
    reset_time = None
    retry_after = None

    # Parse limit
    if "X-RateLimit-Limit" in response.headers:
        try:
            limit = int(response.headers["X-RateLimit-Limit"])
        except ValueError:
            pass

    # Parse remaining
    if "X-RateLimit-Remaining" in response.headers:
        try:
            remaining = int(response.headers["X-RateLimit-Remaining"])
        except ValueError:
            pass

    # Parse reset time
    if "X-RateLimit-Reset" in response.headers:
        try:
            reset_time = float(response.headers["X-RateLimit-Reset"])
        except ValueError:
            pass

    # Parse retry after
    if "Retry-After" in response.headers:
        try:
            retry_after = float(response.headers["Retry-After"])
        except ValueError:
            pass

    return RateLimitInfo(
        limit=limit, remaining=remaining, reset_time=reset_time, retry_after=retry_after
    )


def calculate_sleep_time(
    rate_limit_info: RateLimitInfo,
    buffer_ratio: float = 0.8,
    min_sleep: float = 0.1,
    max_sleep: float = 60.0,
) -> float:
    """
    Calculate how long to sleep based on rate limit information.

    Args:
        rate_limit_info: Rate limit information
        buffer_ratio: Stay below this ratio of the rate limit (0.8 = 80%)
        min_sleep: Minimum sleep time in seconds
        max_sleep: Maximum sleep time in seconds

    Returns:
        Sleep time in seconds
    """
    # If we have an explicit retry-after, use that
    if rate_limit_info.retry_after:
        return min(rate_limit_info.retry_after, max_sleep)

    # If we're near the limit, calculate sleep based on reset time
    if rate_limit_info.is_near_limit(buffer_ratio):
        if rate_limit_info.reset_time:
            # Sleep until reset time
            now = time.time()
            sleep_time = rate_limit_info.reset_time - now

            if sleep_time > 0:
                return min(sleep_time, max_sleep)

        # Default backoff if near limit but no reset time
        return min(5.0, max_sleep)

    # Calculate progressive sleep based on usage ratio
    usage_ratio = rate_limit_info.usage_ratio
    if usage_ratio is not None and usage_ratio > 0.5:
        # Progressive sleep: 0.1s at 50% usage, 2s at 80% usage
        sleep_factor = (usage_ratio - 0.5) / 0.3  # 0.0 to 1.0 from 50% to 80%
        sleep_time = min_sleep + (2.0 - min_sleep) * sleep_factor
        return min(sleep_time, max_sleep)

    # Default minimum sleep
    return min_sleep


def should_retry_on_rate_limit(response: Response) -> bool:
    """Check if request should be retried due to rate limiting."""
    return response.status_code == 429


def get_adaptive_delay(
    consecutive_rate_limits: int, base_delay: float = 1.0, max_delay: float = 60.0
) -> float:
    """
    Calculate adaptive delay based on consecutive rate limit hits.

    Uses exponential backoff with jitter.
    """
    if consecutive_rate_limits <= 0:
        return 0.0

    # Exponential backoff: 1s, 2s, 4s, 8s, etc.
    delay = base_delay * (2 ** (consecutive_rate_limits - 1))

    # Add jitter (±25%)
    import random

    jitter = random.uniform(0.75, 1.25)
    delay *= jitter

    return min(delay, max_delay)


class RateLimiter:
    """
    Intelligent rate limiter that tracks API usage and adapts delays.
    """

    def __init__(
        self, name: str, buffer_ratio: float = 0.8, min_delay: float = 0.1, max_delay: float = 60.0
    ):
        self.name = name
        self.buffer_ratio = buffer_ratio
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.consecutive_rate_limits = 0
        self.last_request_time = 0.0
        self.last_rate_limit_info: RateLimitInfo | None = None

    def process_response(self, response: Response) -> None:
        """Process API response to extract rate limit information."""
        # Reset consecutive rate limits on successful request
        if response.status_code != 429:
            self.consecutive_rate_limits = 0
        else:
            self.consecutive_rate_limits += 1

        # Parse rate limit info based on API
        if "X-Shopify-Shop-Api-Call-Limit" in response.headers:
            self.last_rate_limit_info = parse_shopify_rate_limit(response)
        else:
            self.last_rate_limit_info = parse_generic_rate_limit(response)

        logger.debug(f"{self.name} rate limit info: {self.last_rate_limit_info}")

    def get_delay(self) -> float:
        """Calculate delay before next request."""
        delays = []

        # Base delay since last request
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < self.min_delay:
            delays.append(self.min_delay - time_since_last)

        # Rate limit based delay
        if self.last_rate_limit_info:
            rate_limit_delay = calculate_sleep_time(
                self.last_rate_limit_info, self.buffer_ratio, self.min_delay, self.max_delay
            )
            delays.append(rate_limit_delay)

        # Adaptive delay for consecutive rate limits
        if self.consecutive_rate_limits > 0:
            adaptive_delay = get_adaptive_delay(
                self.consecutive_rate_limits, base_delay=1.0, max_delay=self.max_delay
            )
            delays.append(adaptive_delay)

        return max(delays) if delays else 0.0

    def wait_if_needed(self) -> None:
        """Wait if rate limiting is needed."""
        delay = self.get_delay()

        if delay > 0:
            logger.info(f"{self.name} rate limiting: waiting {delay:.2f}s")
            time.sleep(delay)

        self.last_request_time = time.time()


def create_rate_limiter(integration: str, **kwargs) -> RateLimiter:
    """Create rate limiter for specific integration."""
    return RateLimiter(name=integration, **kwargs)
