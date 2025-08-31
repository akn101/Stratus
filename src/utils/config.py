"""Minimal config utilities for secret retrieval.

Provides a thin wrapper over environment variables so jobs can fetch
tokens without introducing a larger configuration dependency.
"""
from __future__ import annotations

import os


def get_secret(name: str, default: str | None = None) -> str | None:
    """Return a secret value from environment variables.

    Args:
        name: The environment variable name to read.
        default: Optional default if the variable is not set.

    Returns:
        The value of the environment variable or the default.
    """
    return os.getenv(name, default)
