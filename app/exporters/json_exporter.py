"""
JSON exporter for the lead generation pipeline.
"""

import json
from pathlib import Path
from typing import List

from app.core.models import BusinessLead
from app.core.logger import setup_logger


logger = setup_logger("json_exporter")


def export_json(leads: List[BusinessLead], output_path: str) -> str:
    """
    Export a list of BusinessLead records to a formatted JSON file.

    Args:
        leads: List of cleaned/validated BusinessLead records
        output_path: Path for the output JSON file

    Returns:
        Path to the created file
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    data = [lead.model_dump() for lead in leads]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    logger.info(f"JSON exported: {len(leads)} records -> {output_path}")
    return output_path
