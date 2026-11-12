"""
Commodity Fetcher module -- downloads CFTC Disaggregated Commitments of Traders
(Futures Only) data from the Socrata Open Data API.

Dataset: 72hh-3qpy  (Disaggregated COT -- Futures Only)
Host:    publicreporting.cftc.gov

App token: shared with cot_fetcher -- set SOCRATA_APP_TOKEN in .env.
"""

import logging
import os
from datetime import date, timedelta
from typing import Dict, List, Optional, Any

from sodapy import Socrata

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Load app token from Streamlit secrets, env, or .env (shared with cot_fetcher)
# ---------------------------------------------------------------------------
def _load_app_token() -> Optional[str]:
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

COMMODITY_DATASET_ID = "72hh-3qpy"
_FETCH_LIMIT = 5_000


def _get_records(where_clause: str = "") -> List[Dict[str, Any]]:
    """Fetch records from the disaggregated commodity dataset, newest first."""
    try:
        kwargs: Dict[str, Any] = {
            "limit": _FETCH_LIMIT,
            "order": "report_date_as_yyyy_mm_dd DESC",
        }
        futures_filter = "futonly_or_combined = 'FutOnly'"
        kwargs["where"] = f"({where_clause}) AND {futures_filter}" if where_clause else futures_filter
        records = _CLIENT.get(COMMODITY_DATASET_ID, **kwargs)
        logger.debug("Fetched %d commodity records.", len(records) if records else 0)
        return records if records else []
    except Exception:
        logger.exception("Socrata error fetching commodity dataset.")
        return []


def fetch_commodity_records(report_date: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Fetch disaggregated commodity futures records from Socrata.

    If report_date is None, fetches the most recent report available.
    Returns a flat list of raw record dicts.
    """
    try:
        if report_date is not None:
            date_str = report_date.strftime("%Y-%m-%dT00:00:00.000")
            where = f"report_date_as_yyyy_mm_dd = '{date_str}'"
            records = _get_records(where_clause=where)
            if not records:
                date_str2 = report_date.strftime("%Y-%m-%d")
                where2 = (
                    f"report_date_as_yyyy_mm_dd >= '{date_str2}T00:00:00.000' "
                    f"AND report_date_as_yyyy_mm_dd <= '{date_str2}T23:59:59.000'"
                )
                logger.debug("Primary date filter returned 0 records; trying range fallback for %s.", date_str2)
                records = _get_records(where_clause=where2)
        else:
            records = _get_records()

        logger.info("fetch_commodity_records(date=%s): %d records.", report_date, len(records))
        return records
    except Exception:
        logger.exception("Error in fetch_commodity_records(date=%s).", report_date)
        return []


def fetch_commodity_current_week() -> List[Dict[str, Any]]:
    """Return the most-recent week's disaggregated commodity records."""
    logger.info("Fetching current week commodity records.")
    return fetch_commodity_records(report_date=None)


def fetch_commodity_archive_week(release_date: date) -> List[Dict[str, Any]]:
    """
    Return disaggregated commodity records for the report week that
    corresponds to the given release_date (CFTC as-of prior Tuesday).
    """
    offset = (release_date.weekday() - 1) % 7
    report_date = release_date - timedelta(days=offset)
    logger.info("Fetching commodity archive week: release=%s -> report_date=%s.", release_date, report_date)
    return fetch_commodity_records(report_date=report_date)
