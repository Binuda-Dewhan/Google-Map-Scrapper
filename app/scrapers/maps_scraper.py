"""
Google Maps Scraper — Senior-quality browser automation.

This module handles:
  - Navigating Google Maps search results
  - Scrolling to load results (up to max_results limit)
  - Clicking into each business detail pane
  - Extracting all available fields using stable selectors
  - Retry logic, human-like pacing, and JSONL checkpointing
  - Resume support (skips already-scraped URLs on restart)

Design decisions:
  - Single browser session for the entire run (not per search term)
  - Uses aria-label / data-item-id selectors instead of obfuscated class names
  - Coordinates and place_id parsed from the URL itself
  - Address parsed into components using regex
"""

import asyncio
import json
import random
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set, Dict

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from app.core.config import AppSettings, ScraperSettings
from app.core.models import BusinessLead
from app.core.logger import setup_logger


logger = setup_logger("maps_scraper")


# ── Address Parsing ─────────────────────────────────────────────────────────

def parse_address(full_address: str) -> dict:
    """
    Parse a US address string into components.
    Example: "1234 Main St, Houston, TX 77001, USA"
    Returns: {"street": ..., "city": ..., "state": ..., "zip_code": ..., "country": ...}
    """
    result = {"street": None, "city": None, "state": None, "zip_code": None, "country": "US"}

    if not full_address:
        return result

    # Remove trailing country name
    cleaned = full_address.strip()
    for suffix in [", United States", ", USA", ", US"]:
        if cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)]

    # Try to match: street, city, STATE ZIP
    pattern = r'^(.+?),\s*(.+?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$'
    match = re.match(pattern, cleaned)
    if match:
        result["street"] = match.group(1).strip()
        result["city"] = match.group(2).strip()
        result["state"] = match.group(3).strip()
        result["zip_code"] = match.group(4).strip()
        return result

    # Fallback: try city, STATE ZIP (no street)
    pattern2 = r'^(.+?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$'
    match2 = re.match(pattern2, cleaned)
    if match2:
        result["city"] = match2.group(1).strip()
        result["state"] = match2.group(2).strip()
        result["zip_code"] = match2.group(3).strip()
        return result

    # If nothing matches, put the whole thing in street
    result["street"] = cleaned
    return result


def parse_coordinates_from_url(url: str) -> dict:
    """
    Extract latitude and longitude from a Google Maps URL.
    Pattern: @29.7604267,-95.3698028,17z
    """
    result = {"latitude": None, "longitude": None}
    if not url:
        return result

    match = re.search(r'@(-?\d+\.?\d*),(-?\d+\.?\d*)', url)
    if match:
        try:
            result["latitude"] = float(match.group(1))
            result["longitude"] = float(match.group(2))
        except ValueError:
            pass
    return result


def parse_place_id_from_url(url: str) -> Optional[str]:
    """
    Extract place ID from a Google Maps URL.
    Pattern: 0x... in the hex portion, or from the ChIJ... format.
    """
    if not url:
        return None

    # Try the data= parameter which often contains the place id
    match = re.search(r'place/[^/]+/([^/]+)', url)
    if match:
        return match.group(1) if match.group(1).startswith("data=") else None

    # Try the !1s prefix format
    match2 = re.search(r'!1s(0x[a-fA-F0-9]+:[a-fA-F0-9x]+)', url)
    if match2:
        return match2.group(1)

    return None


# ── Human-like Delays ───────────────────────────────────────────────────────

async def human_delay(delay_range: tuple):
    """Wait for a random duration within the given (min, max) range in seconds."""
    delay = random.uniform(delay_range[0], delay_range[1])
    await asyncio.sleep(delay)


# ── Resume Support ──────────────────────────────────────────────────────────

def load_seen_urls(output_file: str) -> Set[str]:
    """
    Read the existing JSONL checkpoint file and return a set of already-scraped URLs.
    This enables resume on restart.
    """
    seen = set()
    path = Path(output_file)
    if not path.exists():
        return seen

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                url = record.get("google_maps_url")
                if url:
                    seen.add(url)
            except json.JSONDecodeError:
                continue

    logger.info(f"Resume: loaded {len(seen)} previously scraped URLs from {output_file}")
    return seen


# ── Main Scraper Class ──────────────────────────────────────────────────────

class GoogleMapsScraper:
    """
    Playwright-based Google Maps business scraper.

    Usage:
        scraper = GoogleMapsScraper(settings, output_file="data/raw/dump.jsonl")
        await scraper.run(location="Houston, Texas", search_tasks=[...])
    """

    def __init__(self, settings: AppSettings, output_file: str):
        self.settings = settings.scraper
        self.output_file = output_file
        self.seen_urls: Set[str] = load_seen_urls(output_file)
        self.stats = {"discovered": 0, "scraped": 0, "skipped": 0, "failed": 0, "duplicates": 0}

    async def run(self, location: str, search_tasks: List[dict]):
        """
        Execute all search tasks using a single browser session.

        Args:
            location: Target location (e.g., "Houston, Texas")
            search_tasks: List of dicts from config.get_search_tasks()
        """
        logger.info(f"=== Starting Google Maps scraper ===")
        logger.info(f"Location: {location}")
        logger.info(f"Search tasks: {len(search_tasks)}")
        logger.info(f"Max results per search: {self.settings.max_results_per_search}")
        logger.info(f"Output file: {self.output_file}")

        # Ensure output directory exists
        Path(self.output_file).parent.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.settings.browser.headless)
            context = await browser.new_context(
                viewport={
                    "width": self.settings.browser.viewport_width,
                    "height": self.settings.browser.viewport_height,
                }
            )
            page = await context.new_page()

            # Handle cookie consent dialogs
            await self._handle_consent(page)

            for i, task in enumerate(search_tasks, 1):
                logger.info(f"--- Task {i}/{len(search_tasks)}: "
                            f"{task['display_name']} -> \"{task['search_term']}\" ---")

                await self._search_and_extract(
                    page=page,
                    location=location,
                    task=task,
                )

                # Pause between search terms
                if i < len(search_tasks):
                    await human_delay(self.settings.delays.between_business_click)

            await browser.close()

        logger.info(f"=== Scraping complete ===")
        logger.info(f"Stats: {self.stats}")

    async def _handle_consent(self, page: Page):
        """Navigate to Maps and handle any consent dialogs."""
        await page.goto("https://www.google.com/maps", wait_until="domcontentloaded")
        await human_delay(self.settings.delays.after_page_load)

        try:
            accept = page.locator("button:has-text('Accept all')")
            if await accept.count() > 0:
                await accept.first.click()
                logger.info("Accepted cookie consent dialog")
                await human_delay(self.settings.delays.after_page_load)
        except Exception:
            pass  # No consent dialog — that's fine

    async def _search_and_extract(self, page: Page, location: str, task: dict):
        """
        Execute a single search query, scroll results, and extract each business.
        """
        query = f"{task['search_term']} in {location}"
        url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}"

        logger.info(f"Navigating to: {query}")
        await page.goto(url, wait_until="domcontentloaded",
                        timeout=self.settings.timeouts.page_load)
        await human_delay(self.settings.delays.after_page_load)

        # Scroll results feed to load businesses
        business_urls = await self._scroll_and_collect_urls(page)

        logger.info(f"Discovered {len(business_urls)} business URLs")
        self.stats["discovered"] += len(business_urls)

        # Filter out already-seen URLs
        new_urls = [u for u in business_urls if u not in self.seen_urls]
        dup_count = len(business_urls) - len(new_urls)
        if dup_count > 0:
            logger.info(f"Skipping {dup_count} already-scraped duplicates")
            self.stats["duplicates"] += dup_count

        # Open the output file in append mode
        with open(self.output_file, "a", encoding="utf-8") as f:
            for idx, biz_url in enumerate(new_urls, 1):
                logger.info(f"  [{idx}/{len(new_urls)}] Extracting details...")

                lead = await self._extract_business(
                    page=page,
                    biz_url=biz_url,
                    task=task,
                )

                if lead:
                    f.write(lead.model_dump_json() + "\n")
                    f.flush()
                    self.seen_urls.add(biz_url)
                    self.stats["scraped"] += 1
                    logger.info(f"  ✓ {lead.business_name} — {lead.extraction_status}")
                else:
                    self.stats["failed"] += 1
                    logger.warning(f"  ✗ Failed to extract: {biz_url[:80]}...")

                # Human-like delay between businesses
                await human_delay(self.settings.delays.between_business_click)

    async def _scroll_and_collect_urls(self, page: Page) -> List[str]:
        """
        Scroll the Maps results feed to load business cards, up to max_results.
        Returns a deduplicated list of business profile URLs.
        """
        feed = page.locator("div[role='feed']")

        try:
            await feed.wait_for(state="visible", timeout=self.settings.timeouts.element_wait)
        except Exception:
            logger.warning("Could not find the results feed. Page may not have loaded correctly.")
            return []

        collected_urls: List[str] = []
        max_results = self.settings.max_results_per_search
        prev_count = 0
        stale_rounds = 0

        logger.info(f"Scrolling results (max {max_results})...")

        while len(collected_urls) < max_results:
            # Scroll to bottom of feed
            await feed.evaluate("el => el.scrollTo(0, el.scrollHeight)")
            await human_delay(self.settings.delays.between_scroll)

            # Check end-of-list indicator
            end_indicator = page.locator("span").filter(has_text="You've reached the end of the list")
            try:
                if await end_indicator.count() > 0 and await end_indicator.first.is_visible():
                    logger.info("Reached the end of the list.")
                    break
            except Exception:
                pass

            # Collect all business links currently in the DOM
            link_elements = await page.locator(
                "a[href*='https://www.google.com/maps/place/']"
            ).all()

            collected_urls = []
            seen_in_scroll = set()
            for el in link_elements:
                href = await el.get_attribute("href")
                if href and href not in seen_in_scroll:
                    seen_in_scroll.add(href)
                    collected_urls.append(href)

            if len(collected_urls) == prev_count:
                stale_rounds += 1
                if stale_rounds >= 3:
                    logger.info("No new results after 3 scroll attempts. Stopping.")
                    break
            else:
                stale_rounds = 0

            prev_count = len(collected_urls)
            logger.info(f"  Loaded {len(collected_urls)} results so far...")

        # Trim to max_results
        return collected_urls[:max_results]

    async def _extract_business(
        self, page: Page, biz_url: str, task: dict
    ) -> Optional[BusinessLead]:
        """
        Navigate to a business detail page and extract all available fields.
        Includes retry logic.
        """
        errors: List[str] = []

        for attempt in range(1, self.settings.retry.max_retries + 1):
            try:
                await page.goto(biz_url, wait_until="domcontentloaded",
                                timeout=self.settings.timeouts.page_load)
                await asyncio.sleep(self.settings.timeouts.detail_render / 1000)

                lead = await self._parse_detail_pane(page, biz_url, task, errors)
                return lead

            except Exception as e:
                err_msg = f"Attempt {attempt} failed: {str(e)}"
                errors.append(err_msg)
                logger.warning(f"  {err_msg}")

                if attempt < self.settings.retry.max_retries:
                    await human_delay(self.settings.retry.retry_delay)

        # All retries exhausted
        logger.error(f"  All {self.settings.retry.max_retries} attempts failed for: {biz_url[:80]}")
        return BusinessLead(
            google_maps_url=biz_url,
            extraction_status="failed",
            extraction_errors=errors,
            data_collected_at=datetime.now().isoformat(),
            industry=task["industry"],
            search_category=task["category"],
            search_term=task["search_term"],
        )

    async def _parse_detail_pane(
        self, page: Page, biz_url: str, task: dict, errors: List[str]
    ) -> BusinessLead:
        """
        Parse all available fields from the Maps business detail pane.
        Uses stable selectors (aria-label, data-item-id).
        """
        name = await self._safe_text(page, "h1")

        # ── Category ────────────────────────────────────────────────────
        category = None
        try:
            # Category button is typically the first button after the name/rating area
            # that contains text like "Dentist", "Restaurant", etc.
            # We look for buttons with a category-related jsaction
            cat_btn = page.locator("button[jsaction*='pane.rating.category']")
            if await cat_btn.count() > 0:
                category = await cat_btn.first.inner_text()
            else:
                # Fallback: look for the category in the info section
                # It's often a span/button near the rating stars
                info_buttons = page.locator("div[role='main'] button").filter(
                    has_not=page.locator("img")
                )
                for i in range(min(await info_buttons.count(), 5)):
                    text = await info_buttons.nth(i).inner_text()
                    # Category text is usually short (1-3 words) and doesn't contain numbers
                    if text and 2 < len(text) < 40 and not any(c.isdigit() for c in text):
                        if text not in ["Directions", "Save", "Share", "Send to phone", "Claim this business"]:
                            category = text
                            break
        except Exception as e:
            errors.append(f"Category extraction: {e}")

        # ── Address ─────────────────────────────────────────────────────
        full_address = None
        try:
            addr_btn = page.locator("button[data-item-id='address']")
            if await addr_btn.count() > 0:
                aria = await addr_btn.first.get_attribute("aria-label")
                if aria:
                    full_address = aria.replace("Address: ", "").strip()
        except Exception as e:
            errors.append(f"Address extraction: {e}")

        address_parts = parse_address(full_address) if full_address else {}

        # ── Phone ───────────────────────────────────────────────────────
        phone = None
        try:
            phone_btn = page.locator("button[data-item-id^='phone:tel:']")
            if await phone_btn.count() > 0:
                aria = await phone_btn.first.get_attribute("aria-label")
                if aria:
                    phone = aria.replace("Phone: ", "").strip()
        except Exception as e:
            errors.append(f"Phone extraction: {e}")

        # ── Website ─────────────────────────────────────────────────────
        website = None
        try:
            web_link = page.locator("a[data-item-id='authority']")
            if await web_link.count() > 0:
                website = await web_link.first.get_attribute("href")
        except Exception as e:
            errors.append(f"Website extraction: {e}")

        # ── Rating & Reviews ────────────────────────────────────────────
        rating = None
        review_count = None
        try:
            # Rating is in a role="img" span with aria-label like "4.8 stars 1,234 Reviews"
            rating_el = page.locator("div[role='main'] span[role='img']").first
            if await rating_el.count() > 0:
                aria = await rating_el.get_attribute("aria-label")
                if aria:
                    # Parse "4.8 stars 1,234 Reviews"
                    r_match = re.search(r'([\d.]+)\s+star', aria)
                    c_match = re.search(r'([\d,]+)\s+[Rr]eview', aria)
                    if r_match:
                        rating = float(r_match.group(1))
                    if c_match:
                        review_count = int(c_match.group(1).replace(",", ""))
        except Exception as e:
            errors.append(f"Rating extraction: {e}")

        # ── Opening Hours ───────────────────────────────────────────────
        opening_hours = None
        try:
            hours_btn = page.locator("button[data-item-id^='oh']")
            if await hours_btn.count() > 0:
                aria = await hours_btn.first.get_attribute("aria-label")
                if aria:
                    opening_hours = aria.strip()
        except Exception as e:
            errors.append(f"Hours extraction: {e}")

        # ── Business Status ─────────────────────────────────────────────
        business_status = "Open"  # Default
        try:
            status_el = page.locator("span:has-text('Temporarily closed')")
            if await status_el.count() > 0:
                business_status = "Temporarily closed"
            else:
                perm_closed = page.locator("span:has-text('Permanently closed')")
                if await perm_closed.count() > 0:
                    business_status = "Permanently closed"
        except Exception as e:
            errors.append(f"Status extraction: {e}")

        # ── Price Level ─────────────────────────────────────────────────
        price_level = None
        try:
            # Price level often appears near the category as "$", "$$", "$$$"
            price_el = page.locator("span[aria-label*='Price']")
            if await price_el.count() > 0:
                price_level = await price_el.first.inner_text()
            else:
                # Fallback: look for $ symbols near category area
                content = await page.content()
                price_match = re.search(r'aria-label="Price: (\$+)"', content)
                if price_match:
                    price_level = price_match.group(1)
        except Exception as e:
            errors.append(f"Price extraction: {e}")

        # ── Social Links & Email ────────────────────────────────────────
        socials = await self._extract_socials(page, errors)
        email = await self._extract_email(page, errors)

        # ── Booking Links ───────────────────────────────────────────────
        booking_url = None
        try:
            # Google Maps sometimes shows "Schedule" or "Book" buttons
            book_link = page.locator("a[data-item-id*='booking'], a[aria-label*='Book'], a[aria-label*='Schedule']")
            if await book_link.count() > 0:
                booking_url = await book_link.first.get_attribute("href")
        except Exception as e:
            errors.append(f"Booking extraction: {e}")

        # ── Coordinates & Place ID from URL ─────────────────────────────
        current_url = page.url
        coords = parse_coordinates_from_url(current_url)
        place_id = parse_place_id_from_url(current_url)

        # Determine extraction status
        status = "success" if name else "partial"
        if not name and not phone and not website:
            status = "failed"

        has_social = any([
            socials.get("facebook_url"),
            socials.get("instagram_url"),
            socials.get("linkedin_url"),
            socials.get("youtube_url"),
        ])

        return BusinessLead(
            business_name=name,
            business_category=category,
            industry=task["industry"],
            search_category=task["category"],
            search_term=task["search_term"],
            address=full_address,
            street=address_parts.get("street"),
            city=address_parts.get("city"),
            state=address_parts.get("state"),
            zip_code=address_parts.get("zip_code"),
            country=address_parts.get("country", "US"),
            latitude=coords.get("latitude"),
            longitude=coords.get("longitude"),
            google_maps_url=current_url,
            place_id=place_id,
            phone=phone,
            website=website,
            email=email,
            google_rating=rating,
            review_count=review_count,
            business_status=business_status,
            price_level=price_level,
            opening_hours=opening_hours,
            facebook_url=socials.get("facebook_url"),
            instagram_url=socials.get("instagram_url"),
            linkedin_url=socials.get("linkedin_url"),
            youtube_url=socials.get("youtube_url"),
            has_social_presence=has_social,
            booking_url=booking_url,
            data_collected_at=datetime.now().isoformat(),
            extraction_status=status,
            extraction_errors=errors if errors else [],
        )

    # ── Helper: Safe Text Extraction ────────────────────────────────────

    async def _safe_text(self, page: Page, selector: str) -> Optional[str]:
        """Safely extract inner text from the first matching element."""
        try:
            loc = page.locator(selector)
            if await loc.count() > 0:
                text = await loc.first.inner_text()
                return text.strip() if text else None
        except Exception:
            pass
        return None

    # ── Helper: Email Extraction ────────────────────────────────────────

    async def _extract_email(self, page: Page, errors: list) -> Optional[str]:
        """Look for email addresses on the Maps detail pane."""
        try:
            # 1. Check for mailto: links
            mailto_elements = await page.locator("a[href^='mailto:']").all()
            for el in mailto_elements:
                href = await el.get_attribute("href")
                if href:
                    email = href.replace("mailto:", "").split("?")[0].strip()
                    if "@" in email:
                        logger.info(f"  [email] Email found (mailto): {email}")
                        return email

            # 2. Regex fallback on visible text
            text = await page.inner_text("div[role='main']")
            pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            matches = re.findall(pattern, text)

            # Filter false positives
            blacklist = ['sentry', 'wixpress', 'google.com', 'googleapis', 'gstatic']
            valid = [m for m in matches if not any(b in m.lower() for b in blacklist)]

            if valid:
                logger.info(f"  [email] Email found (regex): {valid[0]}")
                return valid[0]

        except Exception as e:
            errors.append(f"Email extraction: {e}")

        return None

    # ── Helper: Social Links ────────────────────────────────────────────

    async def _extract_socials(self, page: Page, errors: list) -> Dict[str, Optional[str]]:
        """Extract social media links from the Maps detail pane."""
        socials = {
            "facebook_url": None,
            "instagram_url": None,
            "linkedin_url": None,
            "youtube_url": None,
        }

        social_patterns = {
            "facebook_url": "facebook.com/",
            "instagram_url": "instagram.com/",
            "linkedin_url": "linkedin.com/",
            "youtube_url": "youtube.com/",
        }

        try:
            link_elements = await page.locator("div[role='main'] a[href]").all()
            for el in link_elements:
                href = await el.get_attribute("href")
                if not href:
                    continue
                for key, pattern in social_patterns.items():
                    if pattern in href and socials[key] is None:
                        socials[key] = href
                        logger.info(f"  [social] Social found ({key}): {href[:60]}...")
        except Exception as e:
            errors.append(f"Social extraction: {e}")

        return socials
