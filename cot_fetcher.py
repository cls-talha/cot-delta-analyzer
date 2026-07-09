"""
Fetcher module — downloads COT report pages from CFTC.
Handles current week + archive weeks with error handling.
"""

import requests
from datetime import date, datetime
from typing import Optional, Tuple, List

from config import CURRENT_URL, RELEASE_DATES_2026, get_archive_url


# Timeout for HTTP requests (seconds)
REQUEST_TIMEOUT = 30

# User-Agent to avoid blocks
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def fetch_page(url: str) -> Optional[str]:
    """
    Fetch a URL and return the response text, or None on failure.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"[COT Fetcher] Error fetching {url}: {e}")
        return None


def fetch_current_week() -> Optional[str]:
    """Fetch the current (latest) week's COT report."""
    return fetch_page(CURRENT_URL)


def fetch_archive_week(release_date: date) -> Optional[str]:
    """Fetch an archived week's COT report by release date."""
    url = get_archive_url(release_date)
    return fetch_page(url)


def get_recent_release_dates(
    count: int = 4,
    today: Optional[date] = None,
) -> List[date]:
    """
    From the release schedule, return the most recent `count` past dates.
    Returns a list of dates, from most recent to oldest.
    """
    if today is None:
        today = datetime.now().date()

    past_dates = [d for d in RELEASE_DATES_2026 if d <= today]
    
    # Return up to `count` dates, reversed so most recent is first
    return list(reversed(past_dates[-count:]))
