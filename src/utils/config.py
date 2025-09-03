"""Minimal config utilities for secret retrieval.

Provides a thin wrapper over environment variables so jobs can fetch
tokens without introducing a larger configuration dependency.
"""
from __future__ import annotations

import os

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available, skip loading
    pass


def get_secret(name: str, default: str | None = None) -> str | dict | None:
    """Return a secret value from environment variables.

    Args:
        name: The environment variable name to read, or platform name for structured config.
        default: Optional default if the variable is not set.

    Returns:
        The value of the environment variable, structured config dict, or the default.
    """
    # Handle structured platform configs
    if name == "SHOPIFY":
        shop = os.getenv("SHOPIFY_SHOP")
        access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
        if shop and access_token:
            return {"shop": shop, "access_token": access_token}
        return None
    
    elif name == "SHIPBOB":
        token = os.getenv("SHIPBOB_TOKEN")
        base_url = os.getenv("SHIPBOB_BASE", "https://api.shipbob.com")
        if token:
            return {"token": token, "base_url": base_url}
        return None
    
    elif name == "FREEAGENT":
        access_token = os.getenv("FREEAGENT_ACCESS_TOKEN")
        if access_token:
            return {"access_token": access_token}
        return None
    
    # Handle individual environment variable
    return os.getenv(name, default)
