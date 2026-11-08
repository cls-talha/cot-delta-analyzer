"""
Commodity Parser module — extracts structured Managed Money data from Socrata
Disaggregated COT (Futures Only) API records.

Dataset: 72hh-3qpy

Key columns used:
  market_and_exchange_names           — instrument identifier string
  report_date_as_of_mmdd_yyyy         — report date
  open_interest_all                   — total open interest
  m_money_positions_long_all          — Managed Money long
  m_money_positions_short_all         — Managed Money short
  m_money_positions_spread_all        — Managed Money spread
"""

from typing import Dict, List, Any, Optional
from datetime import datetime

from commodity_config import COMMODITY_INSTRUMENTS


def _safe_float(val: Any) -> float:
    """Safely convert a value to float, returning 0.0 on failure."""
    if val is None:
        return 0.0
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def _format_date(raw_date: str) -> Optional[str]:
    """Convert Socrata ISO date string to human-readable form."""
    if not raw_date:
        return None
    try:
        dt = datetime.strptime(raw_date[:10], "%Y-%m-%d")
        return dt.strftime("%B %-d, %Y")
    except Exception:
        return raw_date


def _select_latest_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only records from the single most-recent report date."""
    if not records:
        return []
    dates = [r.get("report_date_as_yyyy_mm_dd", "") for r in records if r.get("report_date_as_yyyy_mm_dd")]
    if not dates:
        return records
    latest = max(dates)
    return [r for r in records if r.get("report_date_as_yyyy_mm_dd") == latest]


def _match_commodity(market_name: str) -> Optional[str]:
    """
    Match a Socrata market_and_exchange_names string to a COMMODITY_INSTRUMENTS key.
    Returns the display name (e.g. 'Gold') or None.
    """
    upper = market_name.upper()
    for display_name, info in COMMODITY_INSTRUMENTS.items():
        pattern = info["pattern"].upper()
        exchange = info["exchange"].upper()
        if pattern in upper and exchange in upper:
            return display_name
    return None


def parse_commodity_report(records: List[Dict[str, Any]]) -> Dict:
    """
    Parse a list of Socrata disaggregated COT record dicts into structured
    Managed Money commodity data.

    Returns:
        {
            "report_date": "October 28, 2026",
            "instruments": {
                "Gold": {
                    "report_date": "October 28, 2026",
                    "open_interest": 123456.0,
                    "mm_long": 85000.0,
                    "mm_short": 20000.0,
                    "mm_spread": 3000.0,
                },
                ...
            }
        }
    """
    if not records:
        return {"report_date": None, "instruments": {}}

    latest_records = _select_latest_records(records)

    # Determine report date from the latest record set
    report_date_raw = ""
    for r in latest_records:
        v = r.get("report_date_as_yyyy_mm_dd", "")
        if v and v > report_date_raw:
            report_date_raw = v
    report_date = _format_date(report_date_raw)

    instruments: Dict[str, dict] = {}

    for rec in latest_records:
        market_name = rec.get("market_and_exchange_names", "")
        display_name = _match_commodity(market_name)
        if display_name is None:
            continue
        if display_name in instruments:
            continue

        oi       = _safe_float(rec.get("open_interest_all"))
        mm_long  = _safe_float(rec.get("m_money_positions_long_all"))
        mm_short = _safe_float(rec.get("m_money_positions_short_all"))
        mm_spread = _safe_float(rec.get("m_money_positions_spread"))

        instruments[display_name] = {
            "report_date":  report_date,
            "open_interest": oi,
            "mm_long":   mm_long,
            "mm_short":  mm_short,
            "mm_spread": mm_spread,
        }

    return {
        "report_date": report_date,
        "instruments": instruments,
    }
