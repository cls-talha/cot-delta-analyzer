"""
Fetcher module -- downloads COT Traders in Financial Futures (Futures Only)
data from the CFTC via the Socrata Open Data API.

Dataset: gpe5-46if  (Traders in Financial Futures -- Futures Only)
Host:    publicreporting.cftc.gov

App token (optional but recommended):
  Sign up free at https://data.cftc.gov/login, then set
  SOCRATA_APP_TOKEN=<your_token> in the .env file next to this script.
  Without a token, the API is rate-limited to ~1 req/second.
  With a token (free), limits are lifted -- important for weekly batch loads.
"""

import logging
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

from sodapy import Socrata

from config import RELEASE_DATES_2026

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Load optional app token from Streamlit secrets, env, or .env
# ---------------------------------------------------------------------------
def _load_app_token() -> Optional[str]:
    """Read SOCRATA_APP_TOKEN from Streamlit secrets (.toml), env, or .env file."""
    try:
        from supabase_service import get_secret
        token = get_secret("SOCRATA_APP_TOKEN")
        if token:
            return token
    except Exception:
        pass

    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("SOCRATA_APP_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                    return token if token else None
    return None


_APP_TOKEN = _load_app_token()

# ---------------------------------------------------------------------------
# Socrata client
# ---------------------------------------------------------------------------
_CLIENT = Socrata("publicreporting.cftc.gov", _APP_TOKEN, timeout=60)
if _APP_TOKEN:
    logger.info("COT Fetcher: authenticated with Socrata app token.")
else:
    logger.warning(
        "COT Fetcher: no Socrata app token found -- running unauthenticated (rate-limited). "
        "Add SOCRATA_APP_TOKEN=<token> to .env to remove limits."
    )

# Dataset ID for Traders in Financial Futures -- Futures Only
FINANCIAL_DATASET_ID = "gpe5-46if"

# Number of records to pull per request
_FETCH_LIMIT = 5_000


def _get_all_records(dataset_id: str, where_clause: str = "") -> List[Dict[str, Any]]:
    """Fetch all matching records from a Socrata dataset, newest first."""
    try:
        kwargs: Dict[str, Any] = {
            "limit": _FETCH_LIMIT,
            "order": "report_date_as_yyyy_mm_dd DESC",
        }
        futures_filter = "futonly_or_combined = 'FutOnly'"
        kwargs["where"] = f"({where_clause}) AND {futures_filter}" if where_clause else futures_filter
        records = _CLIENT.get(dataset_id, **kwargs)
        logger.debug("Fetched %d records from dataset %s.", len(records) if records else 0, dataset_id)
        return records if records else []
    except Exception:
        logger.exception("Socrata error fetching dataset %s.", dataset_id)
        return []


def fetch_financial_records(report_date: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Fetch financial futures records from Socrata.

    If report_date is None, fetches the most recent report available.
    Returns a list of raw record dicts.
    """
    try:
        if report_date is not None:
            date_str = report_date.strftime("%Y-%m-%dT00:00:00.000")
            where = f"report_date_as_yyyy_mm_dd = '{date_str}'"
            records = _get_all_records(FINANCIAL_DATASET_ID, where_clause=where)
            if not records:
                # Broader fallback for same day
                date_str2 = report_date.strftime("%Y-%m-%d")
                where2 = (
                    f"report_date_as_yyyy_mm_dd >= '{date_str2}T00:00:00.000' "
                    f"AND report_date_as_yyyy_mm_dd <= '{date_str2}T23:59:59.000'"
                )
                logger.debug("Primary date filter returned 0 records; trying range fallback for %s.", date_str2)
                records = _get_all_records(FINANCIAL_DATASET_ID, where_clause=where2)
        else:
            records = _get_all_records(FINANCIAL_DATASET_ID)

        logger.info("fetch_financial_records(date=%s): %d records.", report_date, len(records))
        return records
    except Exception:
        logger.exception("Error in fetch_financial_records(date=%s).", report_date)
        return []


def fetch_current_week() -> List[Dict[str, Any]]:
    """Return the most-recent week's financial futures records from Socrata."""
    logger.info("Fetching current week financial records.")
    return fetch_financial_records(report_date=None)


def fetch_archive_week(release_date: date) -> List[Dict[str, Any]]:
    """
    Return financial futures records for the report week that corresponds
    to the given release_date.  CFTC reports are as-of the prior Tuesday.
    """
    offset = (release_date.weekday() - 1) % 7  # days since last Tuesday
    report_date = release_date - timedelta(days=offset)
    logger.info("Fetching archive week: release=%s -> report_date=%s.", release_date, report_date)
    return fetch_financial_records(report_date=report_date)


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
    result = list(reversed(past_dates[-count:]))
    logger.debug("get_recent_release_dates(count=%d): %s", count, result)
    return result
