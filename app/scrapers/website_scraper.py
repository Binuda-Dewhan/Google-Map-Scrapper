"""
Website Scraper module for Data Enrichment (Part 2).
Uses Playwright to visit business websites and extract contact info.
"""

import asyncio
import re
from typing import List
from playwright.async_api import async_playwright, Page, BrowserContext

from app.core.models import BusinessLead
from app.core.logger import setup_logger
from app.core.config import AppSettings

logger = setup_logger("website_scraper")

# Regex patterns for extraction
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
PHONE_REGEX = re.compile(r'(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})')


class WebsiteScraper:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        # Safely access website_scraper settings using getattr in case they are missing
        scraper_config = getattr(settings, 'website_scraper', {}) if hasattr(settings, 'website_scraper') else {}
        self.concurrency_limit = scraper_config.get('concurrency_limit', 5) if isinstance(scraper_config, dict) else 5
        self.timeout = scraper_config.get('page_timeout', 15000) if isinstance(scraper_config, dict) else 15000
        self.semaphore = asyncio.Semaphore(self.concurrency_limit)
        
    async def enrich_leads(self, leads: List[BusinessLead]) -> List[BusinessLead]:
        """
        Takes a list of leads, filters those with websites, and enriches them.
        """
        leads_to_enrich = [lead for lead in leads if lead.website and lead.website.startswith('http')]
        
        if not leads_to_enrich:
            logger.info("No leads with valid websites to enrich.")
            return leads

        logger.info(f"Enriching {len(leads_to_enrich)} websites concurrently (Limit: {self.concurrency_limit})...")
        
        async with async_playwright() as p:
            # We can use headless=True for website scraping as it's faster and less prone to blocking 
            # than Maps (which requires headed). Websites don't usually block simple headless visits unless they use strict Cloudflare.
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(ignore_https_errors=True)
            
            tasks = [self._process_single_lead(context, lead) for lead in leads_to_enrich]
            await asyncio.gather(*tasks)
            
            await browser.close()
            
        logger.info("Website enrichment complete.")
        return leads

    async def _process_single_lead(self, context: BrowserContext, lead: BusinessLead):
        """Processes a single website, using a semaphore to limit concurrency."""
        async with self.semaphore:
            page = await context.new_page()
            try:
                # Use a fast load state and enforce the strict timeout
                await page.goto(lead.website, wait_until="domcontentloaded", timeout=self.timeout)
                
                # Give a short delay for JS to populate basic DOM elements
                await asyncio.sleep(2)
                
                await self._extract_data(page, lead)
                
            except Exception as e:
                err_msg = str(e).split('\\n')[0]
                logger.debug(f"Failed to scrape {lead.website}: {err_msg}")
            finally:
                await page.close()

    async def _extract_data(self, page: Page, lead: BusinessLead):
        """Extracts emails, phones, and social links from the loaded page."""
        try:
            content = await page.content()
            text_content = await page.evaluate("document.body.innerText")
            
            # 1. Emails
            if not lead.email:
                emails = set(EMAIL_REGEX.findall(text_content))
                # Fallback to source code if innerText fails
                if not emails:
                    emails = set(EMAIL_REGEX.findall(content))
                    
                # Filter out obvious false positives (e.g. image files)
                valid_emails = [e for e in emails if not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.css', '.js'))]
                if valid_emails:
                    lead.email = valid_emails[0]
            
            # 2. Phones
            # If a phone doesn't exist on Maps, or we just want to grab one from the site
            if not lead.phone_from_website:
                phones = PHONE_REGEX.findall(text_content)
                if phones:
                    # Format the first found phone
                    p = phones[0]
                    lead.phone_from_website = f"({p[0]}) {p[1]}-{p[2]}"
                    
            # 3. Socials & Pages
            # Find all links on the page
            hrefs = await page.evaluate("""
                Array.from(document.querySelectorAll('a[href]')).map(a => a.href)
            """)
            
            for href in hrefs:
                href_lower = href.lower()
                if "facebook.com/" in href_lower and not lead.facebook_url:
                    lead.facebook_url = href
                    lead.has_social_presence = True
                elif "instagram.com/" in href_lower and not lead.instagram_url:
                    lead.instagram_url = href
                    lead.has_social_presence = True
                elif "linkedin.com/" in href_lower and not lead.linkedin_url:
                    lead.linkedin_url = href
                    lead.has_social_presence = True
                elif "youtube.com/" in href_lower and not lead.youtube_url:
                    lead.youtube_url = href
                    lead.has_social_presence = True
                elif "twitter.com/" in href_lower or "x.com/" in href_lower:
                    lead.has_social_presence = True 
                
                # Contact/Booking page heuristics
                if "contact" in href_lower and not lead.contact_page:
                    lead.contact_page = href
                if any(x in href_lower for x in ["book", "appointment", "schedule", "calendly", "mindbody"]) and not lead.booking_url:
                    lead.booking_url = href
                    
        except Exception as e:
            logger.debug(f"Data extraction error for {lead.website}: {e}")
