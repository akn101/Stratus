"""
Sync state management for ETL jobs.

Manages high-water marks and sync timestamps to enable incremental processing
and prevent data drift across job runs.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .deps import get_session
from .models import Base

logger = logging.getLogger(__name__)


class SyncState(Base):
    """
    Sync state tracking for incremental ETL jobs.

    Stores high-water marks and metadata for each integration domain
    to enable efficient incremental processing.
    """

    __tablename__ = "sync_state"

    domain = Column(String, primary_key=True)  # e.g., "shopify_orders", "freeagent_invoices"
    last_synced_at = Column(DateTime(timezone=True))  # UTC timestamp of last successful sync
    last_sync_key = Column(String)  # Last processed ID/cursor for pagination
    status = Column(String, default="success")  # success, running, error
    error_count = Column(Integer, default=0)  # Consecutive error count
    error_message = Column(Text)  # Last error message
    sync_metadata = Column(Text)  # JSON metadata (sync stats, etc.)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_sync_state_last_synced_at", "last_synced_at"),
        Index("ix_sync_state_status", "status"),
    )


def get_last_sync_time(domain: str, session: Session | None = None) -> datetime | None:
    """
    Get last successful sync timestamp for a domain.

    Args:
        domain: Sync domain (e.g., "shopify_orders")
        session: Optional database session

    Returns:
        Last sync timestamp (UTC) or None if never synced
    """

    def _query(sess: Session) -> datetime | None:
        sync_state = sess.query(SyncState).filter_by(domain=domain).first()
        if sync_state and sync_state.status == "success":
            return sync_state.last_synced_at
        return None

    if session:
        return _query(session)

    with get_session() as sess:
        return _query(sess)


def update_sync_state(
    domain: str,
    last_synced_at: datetime,
    status: str = "success",
    last_sync_key: str | None = None,
    error_message: str | None = None,
    sync_metadata: dict[str, Any] | None = None,
    session: Session | None = None,
) -> None:
    """
    Update sync state for a domain.

    Args:
        domain: Sync domain
        last_synced_at: Timestamp of successful sync (UTC)
        status: Sync status (success, running, error)
        last_sync_key: Last processed ID/cursor
        error_message: Error message if status is error
        sync_metadata: Additional metadata (will be JSON serialized)
        session: Optional database session
    """
    import json

    # Ensure timezone awareness
    if not last_synced_at.tzinfo:
        last_synced_at = last_synced_at.replace(tzinfo=UTC)

    metadata_json = json.dumps(sync_metadata) if sync_metadata else None

    def _update(sess: Session) -> None:
        # Use upsert to handle concurrent updates
        stmt = pg_insert(SyncState).values(
            domain=domain,
            last_synced_at=last_synced_at,
            status=status,
            last_sync_key=last_sync_key,
            error_count=0 if status == "success" else 1,
            error_message=error_message,
            sync_metadata=metadata_json,
            updated_at=datetime.now(UTC),
        )

        # On conflict, update all fields except domain and created_at
        stmt = stmt.on_conflict_do_update(
            index_elements=["domain"],
            set_={
                "last_synced_at": stmt.excluded.last_synced_at,
                "status": stmt.excluded.status,
                "last_sync_key": stmt.excluded.last_sync_key,
                "error_count": stmt.excluded.error_count
                if status == "success"
                else SyncState.error_count + 1,
                "error_message": stmt.excluded.error_message,
                "sync_metadata": stmt.excluded.sync_metadata,
                "updated_at": stmt.excluded.updated_at,
            },
        )

        sess.execute(stmt)
        sess.commit()

        logger.debug(f"Updated sync state for {domain}: {status} at {last_synced_at}")

    if session:
        _update(session)
    else:
        with get_session() as sess:
            _update(sess)


def mark_sync_running(domain: str, session: Session | None = None) -> None:
    """Mark sync as currently running."""
    update_sync_state(
        domain=domain, last_synced_at=datetime.now(UTC), status="running", session=session
    )


def mark_sync_success(
    domain: str,
    last_synced_at: datetime | None = None,
    last_sync_key: str | None = None,
    sync_metadata: dict[str, Any] | None = None,
    session: Session | None = None,
) -> None:
    """Mark sync as successful."""
    if last_synced_at is None:
        last_synced_at = datetime.now(UTC)

    update_sync_state(
        domain=domain,
        last_synced_at=last_synced_at,
        status="success",
        last_sync_key=last_sync_key,
        sync_metadata=sync_metadata,
        session=session,
    )


def mark_sync_error(domain: str, error_message: str, session: Session | None = None) -> None:
    """Mark sync as failed with error."""
    update_sync_state(
        domain=domain,
        last_synced_at=datetime.now(UTC),
        status="error",
        error_message=error_message,
        session=session,
    )


def get_sync_state(domain: str, session: Session | None = None) -> SyncState | None:
    """Get full sync state for a domain."""

    def _query(sess: Session) -> SyncState | None:
        return sess.query(SyncState).filter_by(domain=domain).first()

    if session:
        return _query(session)

    with get_session() as sess:
        return _query(sess)


def get_all_sync_states(session: Session | None = None) -> dict[str, SyncState]:
    """Get all sync states as a dictionary."""

    def _query(sess: Session) -> dict[str, SyncState]:
        states = sess.query(SyncState).all()
        return {state.domain: state for state in states}

    if session:
        return _query(session)

    with get_session() as sess:
        return _query(sess)


def is_sync_healthy(domain: str, max_age_hours: int = 25) -> bool:
    """
    Check if sync is healthy (recent successful sync).

    Args:
        domain: Sync domain
        max_age_hours: Maximum age of last sync in hours

    Returns:
        True if sync is healthy
    """
    state = get_sync_state(domain)

    if not state or state.status != "success":
        return False

    if not state.last_synced_at:
        return False

    age = datetime.now(UTC) - state.last_synced_at
    return age.total_seconds() < (max_age_hours * 3600)


def cleanup_old_errors(days: int = 7, session: Session | None = None) -> int:
    """
    Clean up old error records.

    Args:
        days: Remove error states older than this many days
        session: Optional database session

    Returns:
        Number of records cleaned up
    """
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(days=days)

    def _cleanup(sess: Session) -> int:
        result = (
            sess.query(SyncState)
            .filter(SyncState.status == "error", SyncState.updated_at < cutoff)
            .delete()
        )
        sess.commit()
        return result

    if session:
        return _cleanup(session)

    with get_session() as sess:
        return _cleanup(sess)
