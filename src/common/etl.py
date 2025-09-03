"""
Shared ETL utilities for data transformation and extraction.

Provides common data parsing, extraction, and transformation helpers
used across Amazon, Shopify, ShipBob, and FreeAgent jobs.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


def extract_id_from_url(url: str) -> str:
    """
    Extract ID from URL path.
    
    Common pattern across APIs to extract resource IDs from URLs.
    
    Args:
        url: URL string containing an ID in the path
        
    Returns:
        Extracted ID as string, empty string if not found
        
    Examples:
        >>> extract_id_from_url("https://api.example.com/v1/orders/12345")
        "12345"
        >>> extract_id_from_url("/admin/api/2024-07/products/6789.json")
        "6789"
    """
    try:
        # Remove query parameters and fragments
        path = urlparse(url).path
        # Extract last numeric-like segment from path
        segments = [s for s in path.split("/") if s]
        for segment in reversed(segments):
            # Remove common file extensions
            segment = re.sub(r'\.(json|xml|html)$', '', segment)
            # Check if segment looks like an ID (numbers, letters, hyphens, underscores)
            if re.match(r'^[a-zA-Z0-9_-]+$', segment):
                return segment
        return ""
    except Exception:
        return ""


def parse_date(date_str: str) -> Optional[datetime]:
    """
    Parse date string supporting common API date formats.
    
    Supports both ISO 8601 and YYYY-MM-DD formats commonly used by APIs.
    
    Args:
        date_str: Date string to parse
        
    Returns:
        Parsed datetime object, None if parsing fails
        
    Examples:
        >>> parse_date("2024-01-15T10:30:00Z")
        datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        >>> parse_date("2024-01-15")
        datetime(2024, 1, 15, 0, 0, 0)
    """
    if not date_str or not isinstance(date_str, str):
        return None
    
    try:
        # Try ISO 8601 format first (most APIs)
        if 'T' in date_str:
            # Handle various ISO formats
            date_str = date_str.replace('Z', '+00:00')  # Convert Z to timezone offset
            return datetime.fromisoformat(date_str)
        else:
            # Try simple YYYY-MM-DD format
            return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        try:
            # Try YYYY-MM-DD HH:MM:SS format
            return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            logger.warning(f"Could not parse date string: {date_str}")
            return None


def json_serialize(obj: Any) -> Optional[str]:
    """
    Safely serialize object to JSON string.
    
    Returns None for empty/invalid objects instead of raising exceptions.
    
    Args:
        obj: Object to serialize
        
    Returns:
        JSON string or None if serialization fails or object is empty
    """
    if obj is None:
        return None
    
    try:
        # Handle empty collections
        if hasattr(obj, '__len__') and len(obj) == 0:
            return None
            
        result = json.dumps(obj, default=str, ensure_ascii=False)
        return result if result and result != 'null' else None
    except (TypeError, ValueError) as e:
        logger.warning(f"JSON serialization failed: {e}")
        return None


def coerce_int(value: Any) -> Optional[int]:
    """
    Safely coerce value to integer.
    
    Handles numeric strings, floats, and None values gracefully.
    
    Args:
        value: Value to coerce to int
        
    Returns:
        Integer value or None if coercion fails
        
    Examples:
        >>> coerce_int("95.0")
        95
        >>> coerce_int("123")
        123
        >>> coerce_int(45.7)
        45
        >>> coerce_int("invalid")
        None
    """
    if value is None:
        return None
    
    try:
        # Handle string representations of floats
        if isinstance(value, str):
            if '.' in value:
                return int(float(value))
            return int(value)
        
        # Handle numeric types
        if isinstance(value, (int, float)):
            return int(value)
            
        return None
    except (ValueError, TypeError):
        return None