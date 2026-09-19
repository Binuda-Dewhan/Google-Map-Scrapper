"""
Deduplication module for business lead records.

Deduplicates by:
  1. google_maps_url (exact match — strongest key)
  2. place_id (if available)
  3. Normalized business_name + address combo (fuzzy fallback)
"""

from typing import List

from app.core.models import BusinessLead
from app.core.logger import setup_logger


logger = setup_logger("deduplicator")


def _normalize_for_comparison(text: str) -> str:
    """Lowercase, strip, remove punctuation for comparison purposes."""
    if not text:
        return ""
    return text.lower().strip().replace(",", "").replace(".", "").replace("'", "")


def deduplicate(leads: List[BusinessLead]) -> List[BusinessLead]:
    """
    Remove duplicate business records.

    Priority order:
      1. Same google_maps_url → keep the first occurrence
      2. Same place_id → keep the first occurrence
      3. Same normalized name + address → keep the first occurrence

    Returns:
        Deduplicated list of BusinessLead records
    """
    seen_urls = set()
    seen_place_ids = set()
    seen_name_address = set()
    unique_leads = []
    dup_count = 0

    for lead in leads:
        # Check by URL
        url = lead.google_maps_url
        if url and url in seen_urls:
            dup_count += 1
            logger.debug(f"Duplicate (URL): {lead.business_name}")
            continue

        # Check by place_id
        pid = lead.place_id
        if pid and pid in seen_place_ids:
            dup_count += 1
            logger.debug(f"Duplicate (place_id): {lead.business_name}")
            continue

        # Check by name + address combo
        name_key = _normalize_for_comparison(lead.business_name or "")
        addr_key = _normalize_for_comparison(lead.address or "")
        combo = f"{name_key}|{addr_key}"

        if combo != "|" and combo in seen_name_address:
            dup_count += 1
            logger.debug(f"Duplicate (name+address): {lead.business_name}")
            continue

        # Not a duplicate — keep it
        if url:
            seen_urls.add(url)
        if pid:
            seen_place_ids.add(pid)
        if combo != "|":
            seen_name_address.add(combo)
        unique_leads.append(lead)

    logger.info(f"Deduplication: {len(leads)} input -> {len(unique_leads)} unique ({dup_count} removed)")
    return unique_leads
