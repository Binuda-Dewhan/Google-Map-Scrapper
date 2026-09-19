"""
Data cleaning module for raw Google Maps scrape output.

Handles:
  - Whitespace normalization
  - Phone number normalization (US format)
  - URL normalization
  - Email normalization
  - State/country standardization
  - Missing value handling
"""

import re
import json
from pathlib import Path
from typing import List, Optional

from app.core.models import BusinessLead
from app.core.logger import setup_logger


logger = setup_logger("cleaner")

# US state abbreviation mapping (common full names → 2-letter)
STATE_MAP = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """Normalize a US phone number to (XXX) XXX-XXXX format."""
    if not phone:
        return None

    digits = re.sub(r'\D', '', phone)

    # Handle +1 prefix
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]

    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"

    # If it doesn't look like a US number, return as-is
    return phone.strip()


def normalize_url(url: Optional[str]) -> Optional[str]:
    """Normalize a URL — lowercase domain, strip trailing slashes."""
    if not url:
        return None

    url = url.strip()

    # Ensure scheme
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # Remove trailing slash
    url = url.rstrip('/')

    return url


def normalize_email(email: Optional[str]) -> Optional[str]:
    """Normalize an email address — lowercase, trim whitespace."""
    if not email:
        return None

    email = email.strip().lower()

    # Basic email format check
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return None

    return email


def normalize_state(state: Optional[str]) -> Optional[str]:
    """Normalize a US state to its 2-letter abbreviation."""
    if not state:
        return None

    state = state.strip()

    # Already abbreviated
    if len(state) == 2 and state.isalpha():
        return state.upper()

    # Try full name lookup
    return STATE_MAP.get(state.lower(), state.upper())


def clean_text(text: Optional[str]) -> Optional[str]:
    """Strip whitespace and normalize a text field."""
    if not text:
        return None
    cleaned = text.strip()
    # Collapse multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned if cleaned else None


def clean_lead(lead: BusinessLead) -> BusinessLead:
    """Apply all cleaning operations to a single BusinessLead record."""

    lead.business_name = clean_text(lead.business_name)
    lead.business_category = clean_text(lead.business_category)
    lead.address = clean_text(lead.address)
    lead.street = clean_text(lead.street)
    lead.city = clean_text(lead.city)
    lead.state = normalize_state(lead.state)
    lead.zip_code = clean_text(lead.zip_code)
    lead.country = lead.country or "US"

    lead.phone = normalize_phone(lead.phone)
    lead.website = normalize_url(lead.website)
    lead.email = normalize_email(lead.email)

    lead.facebook_url = normalize_url(lead.facebook_url)
    lead.instagram_url = normalize_url(lead.instagram_url)
    lead.linkedin_url = normalize_url(lead.linkedin_url)
    lead.youtube_url = normalize_url(lead.youtube_url)
    lead.booking_url = normalize_url(lead.booking_url)

    lead.opening_hours = clean_text(lead.opening_hours)

    return lead


def clean_raw_file(input_path: str, output_path: str) -> List[BusinessLead]:
    """
    Read raw JSONL, clean each record, write cleaned output.

    Args:
        input_path: Path to raw JSONL file
        output_path: Path to write cleaned JSONL

    Returns:
        List of cleaned BusinessLead records
    """
    input_file = Path(input_path)
    if not input_file.exists():
        logger.error(f"Input file not found: {input_path}")
        return []

    cleaned_records = []
    error_count = 0

    with open(input_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                lead = BusinessLead(**data)
                lead = clean_lead(lead)
                cleaned_records.append(lead)
            except Exception as e:
                error_count += 1
                logger.warning(f"Line {line_num}: Failed to parse/clean — {e}")

    logger.info(f"Cleaned {len(cleaned_records)} records ({error_count} errors)")

    # Write cleaned output
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for lead in cleaned_records:
            f.write(lead.model_dump_json() + "\n")

    logger.info(f"Cleaned data written to: {output_path}")
    return cleaned_records
