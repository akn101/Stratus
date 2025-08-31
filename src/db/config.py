"""
Database configuration for Stratus ERP Integration Service.

Loads environment variables and creates SQLAlchemy engine and session factory.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

# Load environment variables from .env file
load_dotenv()


class DatabaseConfig:
    """Database configuration singleton."""

    _engine: Engine | None = None
    _session_factory: sessionmaker | None = None
    _scoped_session: scoped_session | None = None

    @classmethod
    def get_database_url(cls) -> str:
        """Get database URL from environment variables."""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError(
                "DATABASE_URL environment variable is required. "
                "Copy .env.example to .env and set your Supabase connection string."
            )
        return database_url

    @classmethod
    def get_engine(cls) -> Engine:
        """Get SQLAlchemy engine (singleton)."""
        if cls._engine is None:
            database_url = cls.get_database_url()
            cls._engine = create_engine(
                database_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                echo=False,  # Set to True for SQL debugging
            )
        return cls._engine

    @classmethod
    def get_session_factory(cls) -> sessionmaker:
        """Get session factory."""
        if cls._session_factory is None:
            cls._session_factory = sessionmaker(
                bind=cls.get_engine(),
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
            )
        return cls._session_factory

    @classmethod
    def get_scoped_session(cls) -> scoped_session:
        """Get thread-local scoped session."""
        if cls._scoped_session is None:
            cls._scoped_session = scoped_session(cls.get_session_factory())
        return cls._scoped_session


# Convenience exports
engine = DatabaseConfig.get_engine()
SessionLocal = DatabaseConfig.get_session_factory()
ScopedSession = DatabaseConfig.get_scoped_session()
