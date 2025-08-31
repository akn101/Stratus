"""
Configuration loader for Stratus ERP Integration Service.

Loads configuration from YAML files and environment variables with type safety
and nested key access.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Global configuration cache
_config_cache: dict[str, Any] | None = None


def load_config(config_path: str = "config/app.yaml") -> dict[str, Any]:
    """Load configuration from YAML file with environment variable support."""
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    # Load environment variables
    load_dotenv()

    # Load YAML configuration
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_file) as f:
        config = yaml.safe_load(f)

    # Cache the configuration
    _config_cache = config
    return config


def cfg(key: str, default: Any = None) -> Any:
    """
    Get configuration value using dot notation.

    Args:
        key: Dot-separated key path (e.g., "integrations.shopify.enabled")
        default: Default value if key is not found

    Returns:
        Configuration value or default

    Examples:
        cfg("global.timezone", "UTC")
        cfg("integrations.shopify.orders.enabled", True)
    """
    config = load_config()

    # Handle simple key
    if "." not in key:
        return config.get(key, default)

    # Handle nested key with dot notation
    keys = key.split(".")
    value = config

    try:
        for k in keys:
            value = value[k]
        return value
    except (KeyError, TypeError):
        return default


def env(key: str, default: str = None) -> str | None:
    """
    Get environment variable with optional default.

    Args:
        key: Environment variable name
        default: Default value if not found

    Returns:
        Environment variable value or default
    """
    return os.getenv(key, default)


def get_integration_config(integration: str) -> dict[str, Any]:
    """
    Get full configuration for an integration.

    Args:
        integration: Integration name (e.g., "shopify", "freeagent")

    Returns:
        Integration configuration dict
    """
    return cfg(f"integrations.{integration}", {})


def is_integration_enabled(integration: str) -> bool:
    """Check if an integration is enabled."""
    return cfg(f"integrations.{integration}.enabled", False)


def is_job_enabled(integration: str, job: str) -> bool:
    """Check if a specific job is enabled."""
    if not is_integration_enabled(integration):
        return False
    return cfg(f"integrations.{integration}.{job}.enabled", False)


def get_job_config(integration: str, job: str) -> dict[str, Any]:
    """
    Get configuration for a specific job.

    Args:
        integration: Integration name
        job: Job name

    Returns:
        Job configuration dict
    """
    return cfg(f"integrations.{integration}.{job}", {})


def get_job_schedule(integration: str, job: str) -> str | None:
    """Get cron schedule for a job."""
    return cfg(f"integrations.{integration}.{job}.schedule")


def get_lookback_hours(integration: str, job: str, default: int = 24) -> int:
    """Get lookback hours for a job."""
    return cfg(f"integrations.{integration}.{job}.lookback_hours", default)


def get_lookback_days(integration: str, job: str, default: int = 1) -> int:
    """Get lookback days for a job."""
    return cfg(f"integrations.{integration}.{job}.lookback_days", default)


def get_batch_size(integration: str, job: str, default: int = 100) -> int:
    """Get batch size for a job."""
    return cfg(f"integrations.{integration}.{job}.batch_size", default)


def get_database_url() -> str:
    """Get database URL from environment."""
    db_url = env("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is required")
    return db_url


def get_required_env(key: str) -> str:
    """
    Get required environment variable or raise error.

    Args:
        key: Environment variable name

    Returns:
        Environment variable value

    Raises:
        ValueError: If environment variable is not set
    """
    value = env(key)
    if not value:
        raise ValueError(f"{key} environment variable is required")
    return value


# Convenience functions for common environment variables
def get_shopify_config() -> dict[str, str]:
    """Get Shopify API configuration from environment."""
    return {
        "shop": get_required_env("SHOPIFY_SHOP"),
        "access_token": get_required_env("SHOPIFY_ACCESS_TOKEN"),
        "api_version": env("SHOPIFY_API_VERSION", "2024-07"),
    }


def get_shipbob_config() -> dict[str, str]:
    """Get ShipBob API configuration from environment."""
    return {
        "token": get_required_env("SHIPBOB_TOKEN"),
        "base_url": env("SHIPBOB_BASE", "https://api.shipbob.com/2025-07"),
    }


def get_freeagent_config() -> dict[str, str]:
    """Get FreeAgent configuration from environment variables."""
    # Try OAuth first, fall back to direct access token
    client_id = os.getenv("FREEAGENT_CLIENT_ID")
    client_secret = os.getenv("FREEAGENT_CLIENT_SECRET") 
    access_token = os.getenv("FREEAGENT_ACCESS_TOKEN")
    
    if client_id and client_secret:
        config = {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": os.getenv("FREEAGENT_REDIRECT_URI", "http://localhost:8000/auth/freeagent/callback"),
        }
        
        # Include access token if available (for existing tokens)
        if access_token:
            config["access_token"] = access_token
            
        # Include refresh token if available
        refresh_token = os.getenv("FREEAGENT_REFRESH_TOKEN")
        if refresh_token:
            config["refresh_token"] = refresh_token
            
        return config
    elif access_token:
        # Legacy direct token support
        return {"access_token": access_token}
    else:
        raise ValueError("FreeAgent: Either FREEAGENT_CLIENT_ID+CLIENT_SECRET or FREEAGENT_ACCESS_TOKEN is required")


def get_amazon_config() -> dict[str, str]:
    """Get Amazon SP-API configuration from environment."""
    return {
        "access_token": env("AMZ_ACCESS_TOKEN", ""),
        "refresh_token": env("AMZ_REFRESH_TOKEN", ""),
        "client_id": env("AMZ_CLIENT_ID", ""),
        "client_secret": env("AMZ_CLIENT_SECRET", ""),
        "marketplace_ids": env("AMZ_MARKETPLACE_IDS", "").split(","),
    }


# Configuration validation
def validate_config() -> None:
    """Validate configuration and required environment variables."""
    errors = []

    # Check database URL
    try:
        get_database_url()
    except ValueError as e:
        errors.append(str(e))

    # Check enabled integrations
    if is_integration_enabled("shopify"):
        try:
            get_shopify_config()
        except ValueError as e:
            errors.append(f"Shopify: {e}")

    if is_integration_enabled("shipbob"):
        try:
            get_shipbob_config()
        except ValueError as e:
            errors.append(f"ShipBob: {e}")

    if is_integration_enabled("freeagent"):
        try:
            get_freeagent_config()
        except ValueError as e:
            errors.append(f"FreeAgent: {e}")

    if errors:
        raise ValueError(
            "Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors)
        )


def reload_config() -> None:
    """Force reload of configuration cache."""
    global _config_cache
    _config_cache = None
