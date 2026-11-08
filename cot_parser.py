"""
Parser module — extracts structured COT data from Socrata API JSON records.

Dataset: gpe5-46if (Traders in Financial Futures — Futures Only)

Key columns used:
  market_and_exchange_names       — instrument identifier string
  report_date_as_of_mmdd_yyyy     — report date
  open_interest_all               — total open interest
  dealer_positions_long_all       — Dealer long
  dealer_positions_short_all      — Dealer short
  asset_mgr_positions_long_all    — Asset Manager long
  asset_mgr_positions_short_all   — Asset Manager short
  lev_money_positions_long_all    — Leveraged Funds long
  lev_money_positions_short_all   — Leveraged Funds short
"""

from typing import Dict, List, Any, Optional
from config import INSTRUMENTS


def _safe_float(val: Any) -> float:
    """Safely convert a value to float, returning 0.0 on failure."""
    if val is None:
        return 0.0
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def _extract_report_date(records: List[Dict[str, Any]]) -> Optional[str]:
    """Extract the most-recent report date string from the record list."""
    dates = []
    for rec in records:
        raw = rec.get("report_date_as_yyyy_mm_dd", "")
        if raw:
            dates.append(raw)
    if not dates:
        return None
    # Sort ISO date strings descending — pick the latest
    dates.sort(reverse=True)
    # Convert "2026-10-28T00:00:00.000" → "October 28, 2026"
    try:
        from datetime import datetime
        dt = datetime.strptime(dates[0][:10], "%Y-%m-%d")
        return dt.strftime("%B %-d, %Y")
    except Exception:
        return dates[0]


def _match_instrument(market_name: str) -> Optional[str]:
    """
    Match a Socrata market_and_exchange_names string to one of our display names.
    Returns display name (e.g. 'EUR') or None.
    """
    upper = market_name.upper()
    for display_name, info in INSTRUMENTS.items():
        pattern = info["pattern"].upper()
        exchange = info["exchange"].upper()
        if pattern in upper and exchange in upper:
            # Avoid consolidated entries for index instruments
            if "CONSOLIDATED" in upper and display_name in ["SP500 (E-MINI)", "NAS100 (NQ MINI)"]:
                continue
            if display_name == "SP500 (E-MINI)":
                if any(x in upper for x in [
                    "ENERGY", "FINANCIAL", "HEALTH CARE",
                    "INDUSTRIAL", "TECHNOLOGY", "UTILITIES",
                    "COMMUNICATION", "MICRO E-MINI", "ANNUAL DIVIDEND",
                    "QUARTERLY DIVIDEND", "TOTAL RETURN", "S&P 400",
                ]):
                    continue
            if display_name == "NAS100 (NQ MINI)":
                if "MICRO" in upper:
                    continue
            if display_name == "US30 (YM)":
                if "REAL ESTATE" in upper:
                    continue
            if "RUSSELL" in upper and display_name not in []:
                continue
            return display_name
    return None


def _select_latest_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    From a potentially multi-date list of records, keep only those belonging
    to the single most-recent report date.
    """
    if not records:
        return []
    # Determine the latest date
    dates = [r.get("report_date_as_yyyy_mm_dd", "") for r in records if r.get("report_date_as_yyyy_mm_dd")]
    if not dates:
        return records
    latest = max(dates)
    return [r for r in records if r.get("report_date_as_yyyy_mm_dd") == latest]


def parse_report(records: List[Dict[str, Any]]) -> Dict:
    """
    Parse a list of Socrata API record dicts into structured COT data.

    Returns:
        {
            "report_date": "October 28, 2026",
            "instruments": {
                "EUR": {
                    "open_interest": 790076.0,
                    "dealer": {"long": ..., "short": ...},
                    "asset_manager": {"long": ..., "short": ...},
                    "leveraged_funds": {"long": ..., "short": ...},
                },
                ...
            }
        }
    """
    if not records:
        return {"report_date": None, "instruments": {}}

    # Keep only the most-recent date's records
    latest_records = _select_latest_records(records)

    report_date = _extract_report_date(latest_records)
    result: Dict = {
        "report_date": report_date,
        "instruments": {},
    }

    for rec in latest_records:
        market_name = rec.get("market_and_exchange_names", "")
        display_name = _match_instrument(market_name)
        if display_name is None:
            continue
        # Skip duplicates
        if display_name in result["instruments"]:
            continue

        oi = _safe_float(rec.get("open_interest_all"))
        dealer_long  = _safe_float(rec.get("dealer_positions_long_all"))
        dealer_short = _safe_float(rec.get("dealer_positions_short_all"))
        am_long      = _safe_float(rec.get("asset_mgr_positions_long"))
        am_short     = _safe_float(rec.get("asset_mgr_positions_short"))
        lf_long      = _safe_float(rec.get("lev_money_positions_long"))
        lf_short     = _safe_float(rec.get("lev_money_positions_short"))

        if oi == 0.0:
            continue

        result["instruments"][display_name] = {
            "open_interest": oi,
            "dealer": {
                "long": dealer_long,
                "short": dealer_short,
            },
            "asset_manager": {
                "long": am_long,
                "short": am_short,
            },
            "leveraged_funds": {
                "long": lf_long,
                "short": lf_short,
            },
        }

    return result
