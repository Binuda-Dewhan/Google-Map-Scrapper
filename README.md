# US Local Business Lead Generation & Data Enrichment System

## Overview
A robust, automated pipeline designed to discover local US businesses on Google Maps, extract publicly available contact and reputation data, and process it into clean, high-quality lead datasets for marketing and sales outreach. 

Currently, the project encompasses both **Part 1 (Google Maps Scraper)** and **Part 2 (Website Data Enrichment)**.

The system architecture cleanly separates concerns into five stages:
1. **Scraping**: Browser automation to extract unstructured data from Google Maps.
2. **Enrichment**: Concurrent website scraping (via Playwright) to find missing emails, secondary phones, and social links.
3. **Cleaning**: Normalizing formats (phone numbers, states, URLs).
4. **Deduplication & Validation**: Removing duplicates via Google Place IDs and checking data integrity.
5. **Exporting**: Generating professional, ready-to-use CSV, JSON, and Excel files.

## Challenges & Solutions

| Challenge | Solution |
|-----------|----------|
| **Google Anti-Bot Protections** | Implemented a "soft-click" methodology that simulates real human browsing (clicking DOM elements instead of hard-reloading URLs) alongside randomized, human-like delays. |
| **Fragile Selectors & Changing DOMs** | Abandoned fragile CSS class names in favor of highly stable `aria-label` and `data-item-id` attributes to locate data fields. |
| **Unreliable/Malformed Data** | Built a rigorous processing pipeline with Pydantic schemas, regex fallbacks for email/social extraction, and strict validation rules to drop malformed URLs/emails. |
| **Mid-Scrape Crashes** | Developed a checkpointing system that continuously streams raw data to `.jsonl` files. If the script is stopped, it automatically resumes by skipping previously seen URLs. |
| **JS-Heavy Business Websites** | Local businesses often use Wix or Squarespace. We use Playwright to fully render JavaScript and DOM elements instead of basic HTTP requests, ensuring we capture all contact data. |
| **Slow Enrichment Times** | Website scraping can be slow. We implemented an `asyncio.Semaphore` system to aggressively process multiple websites concurrently (e.g., 5-10 tabs at once) in the background. |

## Technologies Used
- **Language**: Python 3.12+
- **Browser Automation**: Playwright (Async)
- **Data Validation**: Pydantic
- **Configuration Engine**: PyYAML
- **Data Manipulation & Export**: Pandas, OpenPyXL (for styled Excel generation)
- **Logging**: Native Python `logging` (structured file & console logging)

## Deliverables & Outputs

The final output is delivered into the `data/final/` directory in three formats:
1. **`*_leads.csv`**: A standard CSV file for importing into CRMs.
2. **`*_leads.json`**: A raw JSON array for API integrations.
3. **`*_leads.xlsx`**: A professionally formatted Excel spreadsheet featuring:
   - Frozen header rows
   - Auto-adjusted column widths
   - Color-coded column groups (e.g., Contact Info in Green, Reputation in Gold)
   - Built-in data filters

**Data Points Extracted:**
- Business Name, Category, Industry
- Full Address (Parsed into Street, City, State, ZIP)
- Coordinates (Latitude/Longitude)
- Phone (Primary from Maps & Secondary from Website)
- Website & Email
- Google Rating, Review Count
- Opening Hours, Price Level, Business Status
- Social Media Links (Facebook, Instagram, LinkedIn, YouTube, X)
- Booking URLs & Contact Page URLs

---

## Installation & Setup

1. **Clone and setup the virtual environment:**
```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

2. **Install dependencies and browser binaries:**
```bash
pip install -r requirements.txt
playwright install chromium
```

3. **Configuration:**
- **`config/categories.yaml`**: Define the industries, categories, and Google Maps search terms.
- **`config/settings.yaml`**: Adjust parameters like `max_results_per_search` (default 50), timeout durations, and human-like delays.

---

## Usage

The system is managed via a single CLI entry point: `main.py`.

```bash
# Scrape EVERYTHING in the categories.yaml file and process the data
python main.py --location "Houston, Texas" --industry all --process

# Scrape multiple industries at once and run Website Enrichment to find emails
python main.py --location "Houston, Texas" --industry health,automotive --enrich --process

# Scrape a single industry (all categories inside it)
python main.py --location "Houston, Texas" --industry health --process

# Scrape a specific category and enrich website data
python main.py --location "Houston, Texas" --industry health --category dental_clinic --enrich --process

# Run enrichment & processing on an existing raw file (skip Maps scraping phase)
python main.py --location "Houston, Texas" --industry health --process-only data/raw/health_houston_texas_raw.jsonl --enrich --process
```

*(Note: While a `--headless` flag exists, running in the default headed mode is strongly recommended for the Maps phase to prevent Google from aggressively blocking the browser. The Website Enrichment phase runs entirely headless in the background automatically.)*
