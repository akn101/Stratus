"""
Database dependency management for Stratus ERP Integration Service.

Provides context managers and utilities for database session handling.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context manager that yields a database session and ensures proper cleanup.

    Automatically handles:
    - Session creation
    - Transaction commit on success
    - Rollback on exception
    - Session cleanup

    Usage:
        with get_session() as session:
            # Database operations here
            result = session.query(Order).all()
            session.add(new_order)
            # Commit happens automatically if no exception
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        raise e
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


@contextmanager
def get_session_no_commit() -> Generator[Session, None, None]:
    """
    Context manager that yields a session without auto-commit.

    Useful for read-only operations or when you need manual transaction control.
    Still handles rollback on exceptions and session cleanup.

    Usage:
        with get_session_no_commit() as session:
            # Read-only operations
            orders = session.query(Order).all()
            # No commit happens automatically
    """
    session = SessionLocal()
    try:
        yield session
    except SQLAlchemyError as e:
        session.rollback()
        raise e
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
