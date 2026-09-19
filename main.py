"""
US Local Business Lead Generation — Main Entry Point

This is the single entry point for Part 1 (Google Maps Scraper).

Usage:
    # Scrape a specific industry in a location
    python main.py --location "Houston, Texas" --industry health

    # Scrape a specific category within an industry
    python main.py --location "Houston, Texas" --industry health --category dental_clinic

    # Run in headless mode
    python main.py --location "Houston, Texas" --industry health --headless

    # Scrape and process (clean + deduplicate + export)
    python main.py --location "Houston, Texas" --industry health --process
"""

import asyncio
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from app.core.config import load_settings, load_categories, get_search_tasks
from app.core.logger import setup_logger
from app.core.models import BusinessLead
from app.scrapers.maps_scraper import GoogleMapsScraper
from app.processing.cleaner import clean_raw_file, clean_lead
from app.processing.deduplicator import deduplicate
from app.processing.validator import validate_leads
from app.exporters.csv_exporter import export_csv
from app.exporters.excel_exporter import export_excel
from app.exporters.json_exporter import export_json


logger = setup_logger("main")


def build_output_filename(location: str, industry: str) -> str:
    """Generate a safe filename from location and industry."""
    safe_loc = location.lower().replace(",", "").replace(" ", "_")
    return f"{industry}_{safe_loc}"


async def run_scraper(args):
    """Execute the Google Maps scraping phase."""
    settings = load_settings()
    categories = load_categories()

    # Override headless setting if CLI flag is provided
    if args.headless:
        settings.scraper.browser.headless = True

    # Build search tasks
    search_tasks = get_search_tasks(
        categories,
        industry_filter=args.industry,
        category_filter=args.category,
    )

    if not search_tasks:
        logger.error(f"No search tasks found for industry='{args.industry}', category='{args.category}'")
        logger.info(f"Available industries: {list(categories.keys())}")
        sys.exit(1)

    logger.info(f"=== US Business Lead Generator - Part 1 ===")
    logger.info(f"Location: {args.location}")
    logger.info(f"Industry: {args.industry}")
    if args.category:
        logger.info(f"Category: {args.category}")
    logger.info(f"Search tasks: {len(search_tasks)}")

    # Output file path
    filename = build_output_filename(args.location, args.industry)
    raw_file = f"{settings.output.raw_dir}/{filename}_raw.jsonl"

    # Run scraper
    scraper = GoogleMapsScraper(settings=settings, output_file=raw_file)
    await scraper.run(location=args.location, search_tasks=search_tasks)

    logger.info(f"Raw data saved to: {raw_file}")
    return raw_file


def run_processing(raw_file: str, location: str, industry: str):
    """Execute the data processing pipeline: clean -> deduplicate -> validate -> export."""
    settings = load_settings()
    filename = build_output_filename(location, industry)

    logger.info("=== Processing Pipeline ===")

    # Step 1: Clean
    cleaned_file = f"{settings.output.cleaned_dir}/{filename}_cleaned.jsonl"
    cleaned_leads = clean_raw_file(raw_file, cleaned_file)

    if not cleaned_leads:
        logger.warning("No records to process after cleaning.")
        return

    # Step 2: Deduplicate
    unique_leads = deduplicate(cleaned_leads)

    # Step 3: Validate
    validated_leads = validate_leads(unique_leads)

    # Step 4: Export
    logger.info("=== Exporting ===")

    for fmt in settings.output.formats:
        output_base = f"{settings.output.final_dir}/{filename}"

        if fmt == "csv":
            export_csv(validated_leads, f"{output_base}_leads.csv")
        elif fmt == "excel":
            export_excel(validated_leads, f"{output_base}_leads.xlsx")
        elif fmt == "json":
            export_json(validated_leads, f"{output_base}_leads.json")

    logger.info(f"=== Pipeline complete - {len(validated_leads)} leads exported ===")


async def main():
    parser = argparse.ArgumentParser(
        description="US Local Business Lead Generation - Google Maps Scraper (Part 1)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --location "Houston, Texas" --industry health
  python main.py --location "Houston, Texas" --industry health --category dental_clinic
  python main.py --location "Houston, Texas" --industry health --process
  python main.py --location "Houston, Texas" --industry health --headless --process
        """,
    )

    parser.add_argument(
        "--location", type=str, required=True,
        help="Target location (e.g., 'Houston, Texas')"
    )
    parser.add_argument(
        "--industry", type=str, required=True,
        help="Industry key from categories.yaml (e.g., 'health', 'automotive')"
    )
    parser.add_argument(
        "--category", type=str, default=None,
        help="Specific category within the industry (e.g., 'dental_clinic')"
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Run browser in headless mode (default: headed)"
    )
    parser.add_argument(
        "--process", action="store_true",
        help="Also run the processing pipeline (clean + deduplicate + export)"
    )
    parser.add_argument(
        "--process-only", type=str, default=None, metavar="RAW_FILE",
        help="Skip scraping - only run processing on an existing raw JSONL file"
    )

    args = parser.parse_args()

    if args.process_only:
        # Just process an existing file
        run_processing(args.process_only, args.location, args.industry)
    else:
        # Run the scraper
        raw_file = await run_scraper(args)

        # Optionally process
        if args.process:
            run_processing(raw_file, args.location, args.industry)
        else:
            logger.info("Tip: Re-run with --process to clean, deduplicate, and export the data.")


if __name__ == "__main__":
    asyncio.run(main())
