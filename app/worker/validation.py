"""Validation utilities for scrape results.

Provides strict schema validation for listings before they're saved to the database,
ensuring data quality and enabling partial-failure tracking.
"""
import logging
from typing import Optional

logger = logging.getLogger("kleinanzeigen-ai")


class ValidationError(Exception):
    """Raised when a listing fails required field validation."""
    pass


def validate_listing(
    title: Optional[str],
    price: Optional[str],
    location: Optional[str],
    url: Optional[str],
) -> None:
    """Validate that a listing has all required fields.
    
    Required fields:
    - title: Must be non-empty string
    - price: Must be non-empty string (can be "N/A" for unknown)
    - location: Must be non-empty string
    - url: Must be non-empty string (unique identifier)
    
    Args:
        title: Listing title
        price: Price string (e.g., "€50", "VB", "N/A")
        location: Location string
        url: Listing URL (primary key for deduplication)
    
    Raises:
        ValidationError: If any required field is missing or empty
    """
    errors = []
    
    if not title or not title.strip():
        errors.append("title is missing or empty")
    elif len(title.strip()) < 3:
        errors.append("title is too short (minimum 3 characters)")
    
    if not price or not price.strip():
        errors.append("price is missing or empty")
    
    if not location or not location.strip():
        errors.append("location is missing or empty")
    
    if not url or not url.strip():
        errors.append("url is missing or empty")
    elif not url.startswith(("http://", "https://")):
        errors.append("url is not a valid HTTP(S) URL")
    
    if errors:
        error_msg = "; ".join(errors)
        raise ValidationError(f"Listing validation failed: {error_msg}")


def validate_and_log(
    title: Optional[str],
    price: Optional[str],
    location: Optional[str],
    url: Optional[str],
    item_index: int = 0,
) -> Optional[str]:
    """Validate a listing and return error message if validation fails.
    
    This is a non-throwing wrapper around validate_listing() that logs
    validation failures and returns the error message instead of raising.
    
    Args:
        title: Listing title
        price: Price string
        location: Location string
        url: Listing URL
        item_index: Index of the item in the scrape batch (for logging)
    
    Returns:
        Error message string if validation failed, None if validation passed
    """
    try:
        validate_listing(title, price, location, url)
        return None
    except ValidationError as e:
        error_msg = str(e)
        logger.warning(
            f"Listing #{item_index} failed validation: {error_msg} "
            f"(title={title[:50] if title else 'None'}...)"
        )
        return error_msg
