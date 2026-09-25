"""
CSV exporter for the lead generation pipeline.
"""

import csv
from pathlib import Path
from typing import List

from app.core.models import BusinessLead
from app.core.logger import setup_logger


logger = setup_logger("csv_exporter")

# Column order for the CSV output
CSV_COLUMNS = [
    "business_name", "business_category", "industry", "search_category",
    "address", "street", "city", "state", "zip_code", "country",
    "latitude", "longitude",
    "phone", "phone_from_website", "website", "email",
    "google_rating", "review_count", "business_status", "price_level", "opening_hours",
    "facebook_url", "instagram_url", "linkedin_url", "youtube_url",
    "has_social_presence", "contact_page", "booking_url",
    "google_maps_url",
    "extraction_status", "data_collected_at",
]


def export_csv(leads: List[BusinessLead], output_path: str) -> str:
    """
    Export a list of BusinessLead records to a CSV file.

    Args:
        leads: List of cleaned/validated BusinessLead records
        output_path: Path for the output CSV file

    Returns:
        Path to the created file
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()

        for lead in leads:
            row = lead.model_dump()
            writer.writerow({k: row.get(k) for k in CSV_COLUMNS})

    logger.info(f"CSV exported: {len(leads)} records -> {output_path}")
    return output_path
