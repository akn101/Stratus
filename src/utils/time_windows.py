"""
Time window utilities for ETL jobs.

Provides helpers for computing lookback windows, aligning timestamps to boundaries,
and managing sync state to avoid drift and ensure consistent data ingestion.
"""

import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(UTC)


def align_to_minute(dt: datetime) -> datetime:
    """Align datetime to minute boundary (zero out seconds/microseconds)."""
    return dt.replace(second=0, microsecond=0)


def align_to_hour(dt: datetime) -> datetime:
    """Align datetime to hour boundary."""
    return dt.replace(minute=0, second=0, microsecond=0)


def align_to_day(dt: datetime) -> datetime:
    """Align datetime to day boundary (midnight UTC)."""
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def compute_lookback_window(
    lookback_hours: int | None = None,
    lookback_days: int | None = None,
    last_sync: datetime | None = None,
    align_to_minutes: bool = True,
) -> tuple[datetime, datetime]:
    """
    Compute time window for incremental sync.

    Args:
        lookback_hours: Hours to look back from now
        lookback_days: Days to look back from now
        last_sync: Last successful sync timestamp
        align_to_minutes: Whether to align timestamps to minute boundaries

    Returns:
        Tuple of (from_time, to_time) in UTC

    Notes:
        - If last_sync is provided and recent, uses that as from_time
        - Otherwise uses lookback_hours/days from current time
        - Always returns UTC timestamps
        - Aligns to minute boundaries by default to avoid drift
    """
    now = utc_now()

    if align_to_minutes:
        now = align_to_minute(now)

    # Determine from_time
    if last_sync and last_sync.tzinfo:
        # Use last sync as starting point with small overlap
        from_time = last_sync - timedelta(minutes=5)  # 5 minute overlap

        # But don't go too far back if last_sync is very old
        max_lookback = None
        if lookback_hours:
            max_lookback = now - timedelta(hours=lookback_hours)
        elif lookback_days:
            max_lookback = now - timedelta(days=lookback_days)

        if max_lookback and from_time < max_lookback:
            from_time = max_lookback
            logger.info(f"Last sync ({last_sync}) is older than max lookback, using {max_lookback}")

    else:
        # Use lookback period from current time
        if lookback_hours:
            from_time = now - timedelta(hours=lookback_hours)
        elif lookback_days:
            from_time = now - timedelta(days=lookback_days)
        else:
            # Default to 24 hours
            from_time = now - timedelta(hours=24)

    if align_to_minutes:
        from_time = align_to_minute(from_time)

    # Ensure from_time is timezone-aware
    if not from_time.tzinfo:
        from_time = from_time.replace(tzinfo=UTC)

    to_time = now

    logger.debug(f"Computed time window: {from_time} to {to_time}")

    return from_time, to_time


def format_iso_timestamp(dt: datetime) -> str:
    """Format datetime as ISO 8601 string in UTC."""
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=UTC)
    elif dt.tzinfo != UTC:
        dt = dt.astimezone(UTC)

    return dt.isoformat().replace("+00:00", "Z")


def parse_iso_timestamp(timestamp: str) -> datetime:
    """Parse ISO 8601 timestamp string to UTC datetime."""
    # Handle Z suffix
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"

    dt = datetime.fromisoformat(timestamp)

    # Ensure UTC timezone
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=UTC)
    elif dt.tzinfo != UTC:
        dt = dt.astimezone(UTC)

    return dt


def compute_batch_windows(
    from_time: datetime, to_time: datetime, batch_hours: int = 24
) -> list[tuple[datetime, datetime]]:
    """
    Split large time window into smaller batch windows.

    Args:
        from_time: Start of overall window
        to_time: End of overall window
        batch_hours: Size of each batch in hours

    Returns:
        List of (batch_from, batch_to) tuples

    Example:
        # Split 7 days into 24-hour batches
        windows = compute_batch_windows(
            from_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            to_time=datetime(2024, 1, 8, tzinfo=timezone.utc),
            batch_hours=24
        )
        # Returns 7 windows of 24 hours each
    """
    windows = []
    current_from = from_time
    batch_delta = timedelta(hours=batch_hours)

    while current_from < to_time:
        current_to = min(current_from + batch_delta, to_time)
        windows.append((current_from, current_to))
        current_from = current_to

    return windows


def is_time_window_valid(from_time: datetime, to_time: datetime) -> bool:
    """Check if time window is valid (from < to, both timezone-aware)."""
    if not from_time.tzinfo or not to_time.tzinfo:
        return False

    return from_time < to_time


def get_time_window_duration(from_time: datetime, to_time: datetime) -> timedelta:
    """Get duration of time window."""
    return to_time - from_time


def format_duration(duration: timedelta) -> str:
    """Format timedelta as human-readable string."""
    total_seconds = int(duration.total_seconds())

    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}m{seconds}s"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}h{minutes}m"
    else:
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        return f"{days}d{hours}h"
