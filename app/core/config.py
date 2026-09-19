"""
Configuration loader for the US Business Lead Generator.

Loads settings from config/settings.yaml and config/categories.yaml,
and provides typed access through Pydantic models.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel


# ── Pydantic Settings Models ────────────────────────────────────────────────

class BrowserSettings(BaseModel):
    headless: bool = False
    viewport_width: int = 1280
    viewport_height: int = 900


class TimeoutSettings(BaseModel):
    page_load: int = 30000
    element_wait: int = 10000
    detail_render: int = 3000


class DelaySettings(BaseModel):
    between_scroll: Tuple[float, float] = (1.5, 3.0)
    between_business_click: Tuple[float, float] = (2.0, 4.0)
    after_page_load: Tuple[float, float] = (1.0, 2.0)


class RetrySettings(BaseModel):
    max_retries: int = 2
    retry_delay: Tuple[float, float] = (3.0, 5.0)


class ScraperSettings(BaseModel):
    max_results_per_search: int = 50
    browser: BrowserSettings = BrowserSettings()
    timeouts: TimeoutSettings = TimeoutSettings()
    delays: DelaySettings = DelaySettings()
    retry: RetrySettings = RetrySettings()


class OutputSettings(BaseModel):
    raw_dir: str = "data/raw"
    cleaned_dir: str = "data/cleaned"
    final_dir: str = "data/final"
    log_dir: str = "logs"
    formats: List[str] = ["csv", "excel", "json"]


class AppSettings(BaseModel):
    scraper: ScraperSettings = ScraperSettings()
    output: OutputSettings = OutputSettings()


# ── Category Model ──────────────────────────────────────────────────────────

class CategoryConfig(BaseModel):
    display_name: str
    search_terms: List[str]


# ── Loaders ─────────────────────────────────────────────────────────────────

def _find_project_root() -> Path:
    """Walk up from this file to find the project root (contains config/)."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "config").is_dir():
            return current
        current = current.parent
    raise FileNotFoundError("Could not find project root (directory containing config/)")


def load_settings(settings_path: Optional[str] = None) -> AppSettings:
    """Load application settings from config/settings.yaml."""
    if settings_path is None:
        root = _find_project_root()
        settings_path = str(root / "config" / "settings.yaml")

    path = Path(settings_path)
    if not path.exists():
        # Return defaults if no settings file exists
        return AppSettings()

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return AppSettings(**raw)


def load_categories(categories_path: Optional[str] = None) -> Dict[str, Dict[str, CategoryConfig]]:
    """
    Load the category library from config/categories.yaml.

    Returns:
        Dict mapping industry_key -> {category_key -> CategoryConfig}
        Example: {"health": {"dental_clinic": CategoryConfig(display_name="Dental Clinics", search_terms=[...])}}
    """
    if categories_path is None:
        root = _find_project_root()
        categories_path = str(root / "config" / "categories.yaml")

    path = Path(categories_path)
    if not path.exists():
        raise FileNotFoundError(f"Categories config not found: {categories_path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    result: Dict[str, Dict[str, CategoryConfig]] = {}
    for industry_key, categories in raw.items():
        result[industry_key] = {}
        for cat_key, cat_data in categories.items():
            result[industry_key][cat_key] = CategoryConfig(**cat_data)

    return result


def get_search_tasks(
    categories: Dict[str, Dict[str, CategoryConfig]],
    industry_filter: Optional[str] = None,
    category_filter: Optional[str] = None
) -> List[dict]:
    """
    Build a flat list of search tasks from the category library.

    Each task is a dict:
        {"industry": str, "category": str, "display_name": str, "search_term": str}

    Optionally filter by industry and/or category.
    """
    tasks = []
    for industry_key, cats in categories.items():
        if industry_filter and industry_key != industry_filter:
            continue
        for cat_key, cat_config in cats.items():
            if category_filter and cat_key != category_filter:
                continue
            for term in cat_config.search_terms:
                tasks.append({
                    "industry": industry_key,
                    "category": cat_key,
                    "display_name": cat_config.display_name,
                    "search_term": term,
                })
    return tasks
