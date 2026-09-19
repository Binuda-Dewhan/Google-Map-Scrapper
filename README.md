# US Local Business Lead Generation & Data Enrichment System

A browser automation pipeline for discovering local US businesses on Google Maps, extracting publicly available contact and reputation data, and exporting clean lead datasets.

**Part 1** — Google Maps scraper (this version).
**Part 2** — Website enrichment (planned).

## Project Structure

```text
us-business-lead-generator/
├── app/
│   ├── core/              # Config, models, logging
│   ├── scrapers/          # Playwright-based scraper
│   ├── processing/        # Cleaning, deduplication, validation
│   └── exporters/         # CSV, Excel, JSON exporters
├── config/
│   ├── categories.yaml    # Industry/category library with search terms
│   └── settings.yaml      # Scraper settings (timeouts, delays, limits)
├── data/
│   ├── raw/               # Raw JSONL from scraper (checkpoint files)
│   ├── cleaned/           # Cleaned JSONL
│   └── final/             # Exported CSV/Excel/JSON
├── logs/                  # Timestamped log files
├── tests/
├── main.py                # Single entry point
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Setup

```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
# Scrape dental clinics in Houston (headed mode, max 50 per term)
python main.py --location "Houston, Texas" --industry health --category dental_clinic

# Scrape all health categories in Houston
python main.py --location "Houston, Texas" --industry health

# Scrape + process in one step
python main.py --location "Houston, Texas" --industry health --process

# Process an existing raw file only (skip scraping)
python main.py --location "Houston, Texas" --industry health --process-only data/raw/health_houston_texas_raw.jsonl

# Headless mode
python main.py --location "Houston, Texas" --industry health --headless --process
```

## Configuration

- **`config/categories.yaml`** — Define industries, categories, and their Google Maps search terms.
- **`config/settings.yaml`** — Adjust max results, timeouts, human-like delays, and retry behavior.

## Data Pipeline

```
Google Maps → Raw JSONL → Clean → Deduplicate → Validate → CSV/Excel/JSON
```

## Output

Final exports are saved in `data/final/` in three formats:
- `*_leads.csv`
- `*_leads.xlsx` (formatted with filters, frozen header, color-coded columns)
- `*_leads.json`
