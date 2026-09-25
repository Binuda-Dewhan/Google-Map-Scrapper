"""
Pydantic data models for the US Business Lead Generator.

BusinessLead represents a single business record collected from Google Maps.
All fields are Optional because not every business exposes every data point.
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class BusinessLead(BaseModel):
    """
    Core data model for a business lead extracted from Google Maps.

    Fields are grouped by data domain and annotated with their expected source.
    """

    # ── Business Information ────────────────────────────────────────────
    business_name: Optional[str] = Field(None, description="Business display name from Google Maps")
    business_category: Optional[str] = Field(None, description="Primary category shown on Maps (e.g., 'Dentist')")
    industry: Optional[str] = Field(None, description="Industry group from our category library")
    search_category: Optional[str] = Field(None, description="Category key used for this search (e.g., 'dental_clinic')")
    search_term: Optional[str] = Field(None, description="Exact search term used (e.g., 'dental clinic')")

    # ── Address ─────────────────────────────────────────────────────────
    address: Optional[str] = Field(None, description="Full address as shown on Maps")
    street: Optional[str] = Field(None, description="Parsed street address")
    city: Optional[str] = Field(None, description="Parsed city")
    state: Optional[str] = Field(None, description="Parsed state abbreviation")
    zip_code: Optional[str] = Field(None, description="Parsed ZIP code")
    country: Optional[str] = Field(None, description="Country (defaults to US)")
    latitude: Optional[float] = Field(None, description="Latitude from Maps URL")
    longitude: Optional[float] = Field(None, description="Longitude from Maps URL")

    # ── Identifiers ─────────────────────────────────────────────────────
    google_maps_url: Optional[str] = Field(None, description="Direct URL to the Maps listing")
    place_id: Optional[str] = Field(None, description="Google Place ID extracted from URL")

    # ── Contact ─────────────────────────────────────────────────────────
    phone: Optional[str] = Field(None, description="Phone number from Maps")
    phone_from_website: Optional[str] = Field(None, description="Secondary/direct phone found on website")
    website: Optional[str] = Field(None, description="Website URL from Maps")
    email: Optional[str] = Field(None, description="Email if found on Maps or Website")
    contact_page: Optional[str] = Field(None, description="Contact Us page URL found on website")

    # ── Reputation & Status ─────────────────────────────────────────────
    google_rating: Optional[float] = Field(None, description="Star rating (1.0–5.0)")
    review_count: Optional[int] = Field(None, description="Total number of reviews")
    business_status: Optional[str] = Field(None, description="Open/Closed/Temporarily closed")
    price_level: Optional[str] = Field(None, description="Price level ($, $$, $$$)")
    opening_hours: Optional[str] = Field(None, description="Opening hours summary text")

    # ── Digital Presence (from Maps) ────────────────────────────────────
    facebook_url: Optional[str] = Field(None, description="Facebook page link if shown on Maps")
    instagram_url: Optional[str] = Field(None, description="Instagram link if shown on Maps")
    linkedin_url: Optional[str] = Field(None, description="LinkedIn link if shown on Maps")
    youtube_url: Optional[str] = Field(None, description="YouTube link if shown on Maps")
    has_social_presence: Optional[bool] = Field(None, description="Whether any social link was found")

    # ── Booking ─────────────────────────────────────────────────────────
    booking_url: Optional[str] = Field(None, description="Booking/appointment link if shown on Maps")

    # ── Extraction Metadata ─────────────────────────────────────────────
    data_collected_at: Optional[str] = Field(None, description="ISO timestamp of extraction")
    extraction_status: Optional[str] = Field(None, description="success | partial | failed")
    extraction_errors: Optional[List[str]] = Field(default_factory=list, description="List of errors during extraction")
    data_source: str = Field(default="google_maps", description="Source identifier")
