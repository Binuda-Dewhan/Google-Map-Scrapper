"""
Data validation module for business lead records.

Validates:
  - Email format
  - URL format
  - Phone format
  - Required fields
  - Data types (rating range, review count non-negative)

Records that fail critical validation are flagged, not discarded.
"""

import re
from typing import List, Tuple

from app.core.models import BusinessLead
from app.core.logger import setup_logger


logger = setup_logger("validator")


def _is_valid_email(email: str) -> bool:
    """Check if a string looks like a valid email address."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def _is_valid_url(url: str) -> bool:
    """Check if a string looks like a valid URL."""
    pattern = r'^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return bool(re.match(pattern, url))


def _is_valid_phone(phone: str) -> bool:
    """Check if a string looks like a valid US phone number."""
    # After normalization, should be (XXX) XXX-XXXX or at least have 10+ digits
    digits = re.sub(r'\D', '', phone)
    return len(digits) >= 10


def validate_lead(lead: BusinessLead) -> Tuple[BusinessLead, List[str]]:
    """
    Validate a single BusinessLead record.

    Returns:
        Tuple of (lead, list_of_warnings)
        The lead is returned with invalid fields cleared (set to None).
    """
    warnings = []

    # ── Required field check ────────────────────────────────────────────
    if not lead.business_name:
        warnings.append("Missing business_name")

    # ── Email validation ────────────────────────────────────────────────
    if lead.email and not _is_valid_email(lead.email):
        warnings.append(f"Invalid email cleared: {lead.email}")
        lead.email = None

    # ── URL validation ──────────────────────────────────────────────────
    if lead.website and not _is_valid_url(lead.website):
        warnings.append(f"Invalid website URL cleared: {lead.website}")
        lead.website = None

    for url_field in ["facebook_url", "instagram_url", "linkedin_url", "youtube_url", "booking_url"]:
        val = getattr(lead, url_field)
        if val and not _is_valid_url(val):
            warnings.append(f"Invalid {url_field} cleared: {val}")
            setattr(lead, url_field, None)

    # ── Phone validation ────────────────────────────────────────────────
    if lead.phone and not _is_valid_phone(lead.phone):
        warnings.append(f"Suspicious phone format: {lead.phone}")
        # Don't clear — just flag it

    # ── Rating range check ──────────────────────────────────────────────
    if lead.google_rating is not None:
        if not (0.0 <= lead.google_rating <= 5.0):
            warnings.append(f"Rating out of range: {lead.google_rating}")
            lead.google_rating = None

    # ── Review count check ──────────────────────────────────────────────
    if lead.review_count is not None and lead.review_count < 0:
        warnings.append(f"Negative review count: {lead.review_count}")
        lead.review_count = None

    return lead, warnings


def validate_leads(leads: List[BusinessLead]) -> List[BusinessLead]:
    """
    Validate all leads in a list.
    Logs warnings but keeps all records (with invalid fields cleared).

    Returns:
        Validated list of BusinessLead records
    """
    validated = []
    total_warnings = 0

    for lead in leads:
        lead, warnings = validate_lead(lead)
        validated.append(lead)
        if warnings:
            total_warnings += len(warnings)
            for w in warnings:
                logger.warning(f"  {lead.business_name or 'Unknown'}: {w}")

    logger.info(f"Validation complete: {len(validated)} records, {total_warnings} warnings")
    return validated
