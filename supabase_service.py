"""
Supabase Database Service for COT Analyzer.

Handles weekly data synchronization for the 4 primary tables:
  1. Commodity COT (Disaggregated Managed Money) -> 'commodity_cot'
  2. Current Week Overview                       -> 'cot_current_week_overview'
  3. Leveraged Funds Breakdown                  -> 'cot_leveraged_funds_breakdown'
  4. COT Detailed Breakdown                     -> 'cot_detailed_breakdown'

Supports:
  - Streamlit secrets (secrets.toml) on Streamlit Cloud & local
  - Zero duplicate pushing (checks if week already exists before sending)
  - Zero disruption to local cache or existing CSV files
  - Pure HTTP / requests-based PostgREST API (no heavy dependencies)
"""

import json
import logging
import os
import urllib.parse
from typing import Any, Dict, List, Optional, Set
import requests

logger = logging.getLogger(__name__)

# Session cache to prevent repeated HTTP existence checks on every rerun
_CHECKED_EXISTING_DATES: Set[str] = set()


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Retrieve secret from Streamlit secrets, environment variables,
    .streamlit/secrets.toml, or .env file (in that order).
    """
    # 1. Streamlit secrets (Streamlit Cloud & local streamlit run)
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            if key in st.secrets:
                return str(st.secrets[key])
            if "supabase" in st.secrets and isinstance(st.secrets["supabase"], dict):
                sub_key = key.replace("SUPABASE_", "").lower()
                if sub_key in st.secrets["supabase"]:
                    return str(st.secrets["supabase"][sub_key])
    except Exception:
        pass

    # 2. Environment variables
    val = os.environ.get(key)
    if val:
        return val

    # 3. Read .streamlit/secrets.toml directly (for scripts running outside Streamlit)
    toml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit", "secrets.toml")
    if os.path.exists(toml_path):
        try:
            try:
                import tomllib
                with open(toml_path, "rb") as f:
                    data = tomllib.load(f)
            except ImportError:
                data = {}
                with open(toml_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            data[k.strip()] = v.strip().strip('"').strip("'")

            if key in data:
                return str(data[key])
            if "supabase" in data and isinstance(data["supabase"], dict):
                sub_key = key.replace("SUPABASE_", "").lower()
                if sub_key in data["supabase"]:
                    return str(data["supabase"][sub_key])
        except Exception as e:
            logger.debug("Error reading secrets.toml: %s", e)

    # 4. Fallback: .env file
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(f"{key}="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass

    return default


def is_supabase_configured() -> bool:
    """Return True if SUPABASE_URL and SUPABASE_KEY are configured."""
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY")
    return bool(url and key and "your-project" not in url)


def _get_headers() -> Dict[str, str]:
    """Get HTTP headers for Supabase PostgREST API requests."""
    key = get_secret("SUPABASE_KEY", "")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }


def _clean_val(val: Any) -> Optional[Any]:
    """Convert numpy / pandas NaN or invalid types to None (null in JSON).
    Also converts whole floats (e.g. 1524.0) to integers (1524) to satisfy Postgres.
    """
    if val is None:
        return None
    try:
        import math
        if isinstance(val, (float, int)) and math.isnan(val):
            return None
    except Exception:
        pass
    s_val = str(val).strip().lower()
    if s_val in ("nan", "none", "null", "nat", ""):
        return None
    if isinstance(val, (int, float)):
        if isinstance(val, float) and val.is_integer():
            return int(val)
        return val
    try:
        s = str(val).replace(",", "").replace("%", "").strip()
        f = float(s)
        if f.is_integer():
            return int(f)
        return f
    except (ValueError, TypeError):
        return str(val)


def check_report_date_exists(table_name: str, report_date: str) -> bool:
    """
    Check Supabase to see if a report_date already exists in the given table.
    Uses session cache if already verified in this session to minimize requests.
    """
    cache_key = f"{table_name}:{report_date}"
    if cache_key in _CHECKED_EXISTING_DATES:
        return True

    url = get_secret("SUPABASE_URL")
    if not url or not is_supabase_configured():
        return False

    base_url = url.rstrip("/")
    encoded_date = urllib.parse.quote(report_date)
    endpoint = f"{base_url}/rest/v1/{table_name}?select=report_date&report_date=eq.{encoded_date}&limit=1"

    try:
        headers = _get_headers()
        res = requests.get(endpoint, headers=headers, timeout=8)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                _CHECKED_EXISTING_DATES.add(cache_key)
                return True
        elif res.status_code == 404:
            logger.warning("Supabase table '%s' not found. Please create it using supabase_schema.sql.", table_name)
        else:
            logger.warning("Supabase check error on %s: HTTP %s - %s", table_name, res.status_code, res.text)
    except Exception as e:
        logger.warning("Supabase connection error checking %s: %s", table_name, e)

    return False


def push_records(table_name: str, records: List[Dict[str, Any]]) -> bool:
    """
    Upsert records into Supabase using PostgREST.
    """
    if not records or not is_supabase_configured():
        return False

    url = get_secret("SUPABASE_URL")
    if not url:
        return False

    base_url = url.rstrip("/")
    endpoint = f"{base_url}/rest/v1/{table_name}"
    headers = _get_headers()

    try:
        res = requests.post(endpoint, headers=headers, data=json.dumps(records), timeout=15)
        if res.status_code in (200, 201):
            logger.info("Successfully pushed %d records to '%s'.", len(records), table_name)
            return True
        else:
            logger.error("Failed to push to '%s': HTTP %s - %s", table_name, res.status_code, res.text)
            return False
    except Exception as e:
        logger.error("Exception pushing records to '%s': %s", table_name, e)
        return False


def push_weekly_data_to_supabase(
    comm_current_date: Optional[str],
    df_commodity: Optional[Any],
    fin_current_date: Optional[str],
    df_consolidated: Optional[Any],
    df_lf_breakdown: Optional[Any],
    df_detailed: Optional[Any],
) -> Dict[str, str]:
    """
    Push new weekly data to Supabase ONLY if not already present.
    Returns a status dict describing what was pushed or skipped.
    """
    status: Dict[str, str] = {}

    if not is_supabase_configured():
        logger.debug("Supabase is not configured (missing SUPABASE_URL / SUPABASE_KEY). Skipping push.")
        return {"status": "unconfigured"}

    # 1. Commodity COT (Disaggregated Managed Money)
    if comm_current_date and df_commodity is not None and not df_commodity.empty:
        table_name = "commodity_cot"
        if check_report_date_exists(table_name, comm_current_date):
            status["commodity_cot"] = f"already_exists ({comm_current_date})"
        else:
            records = []
            for commodity, row in df_commodity.iterrows():
                records.append({
                    "report_date": comm_current_date,
                    "commodity": str(commodity),
                    "long_pos": _clean_val(row.get("Long")),
                    "short_pos": _clean_val(row.get("Short")),
                    "spread": _clean_val(row.get("Spread")),
                    "net_pos": _clean_val(row.get("Net")),
                    "long_pct": _clean_val(row.get("Long %")),
                    "short_pct": _clean_val(row.get("Short %")),
                    "open_interest": _clean_val(row.get("Open Int.")),
                    "delta_net": _clean_val(row.get("Δ Net")),
                    "delta_long": _clean_val(row.get("Δ Long")),
                    "delta_short": _clean_val(row.get("Δ Short")),
                })
            if push_records(table_name, records):
                _CHECKED_EXISTING_DATES.add(f"{table_name}:{comm_current_date}")
                status["commodity_cot"] = f"pushed ({comm_current_date})"

    # 2. Financial / Forex tables
    if fin_current_date:
        # Table 2: Current Week Overview
        if df_consolidated is not None and not df_consolidated.empty:
            table_name = "cot_current_week_overview"
            if check_report_date_exists(table_name, fin_current_date):
                status["cot_current_week_overview"] = f"already_exists ({fin_current_date})"
            else:
                records = []
                for currency, row in df_consolidated.iterrows():
                    records.append({
                        "report_date": fin_current_date,
                        "currency": str(currency),
                        "lf_delta": _clean_val(row.get("LF Δ")),
                        "am_delta": _clean_val(row.get("AM Δ")),
                        "di_delta": _clean_val(row.get("DI Δ")),
                        "lf_am_long_positions": _clean_val(row.get("LF+AM Long Positions")),
                        "lf_am_short_positions": _clean_val(row.get("LF+AM Short Positions")),
                        "total_oi": _clean_val(row.get("Total OI")),
                        "delta_long_positions": _clean_val(row.get("Δ Long Positions")),
                        "delta_short_positions": _clean_val(row.get("Δ Short Positions")),
                    })
                if push_records(table_name, records):
                    _CHECKED_EXISTING_DATES.add(f"{table_name}:{fin_current_date}")
                    status["cot_current_week_overview"] = f"pushed ({fin_current_date})"

        # Table 3: Leveraged Funds Breakdown
        if df_lf_breakdown is not None and not df_lf_breakdown.empty:
            table_name = "cot_leveraged_funds_breakdown"
            if check_report_date_exists(table_name, fin_current_date):
                status["cot_leveraged_funds_breakdown"] = f"already_exists ({fin_current_date})"
            else:
                records = []
                for currency, row in df_lf_breakdown.iterrows():
                    records.append({
                        "report_date": fin_current_date,
                        "currency": str(currency),
                        "net_positions": _clean_val(row.get("Net Positions")),
                        "net_percent": _clean_val(row.get("Net Percent")),
                        "net_percent_lf": _clean_val(row.get("Net Percent LF")),
                        "net_pct_lf_delta": _clean_val(row.get("Net % LF Δ")),
                        "lf_long_delta": _clean_val(row.get("LF longs Δ")),
                        "lf_short_delta": _clean_val(row.get("LF short Δ")),
                    })
                if push_records(table_name, records):
                    _CHECKED_EXISTING_DATES.add(f"{table_name}:{fin_current_date}")
                    status["cot_leveraged_funds_breakdown"] = f"pushed ({fin_current_date})"

        # Table 4: COT Detailed Breakdown
        if df_detailed is not None and not df_detailed.empty:
            table_name = "cot_detailed_breakdown"
            if check_report_date_exists(table_name, fin_current_date):
                status["cot_detailed_breakdown"] = f"already_exists ({fin_current_date})"
            else:
                records = []
                for currency, row in df_detailed.iterrows():
                    records.append({
                        "report_date": fin_current_date,
                        "currency": str(currency),
                        "delta_total_oi": _clean_val(row.get("Δ Total Open Interest")),
                        "delta_lf_oi": _clean_val(row.get("Δ LF Open Interest")),
                        "delta_lf_longs_usd_b": _clean_val(row.get("Δ LF Longs ($B)")),
                        "delta_lf_shorts_usd_b": _clean_val(row.get("Δ LF Shorts ($B)")),
                        "delta_am_longs_usd_b": _clean_val(row.get("Δ AM Longs ($B)")),
                        "delta_am_shorts_usd_b": _clean_val(row.get("Δ AM Shorts ($B)")),
                        "am_long_delta": _clean_val(row.get("AM long Δ")),
                        "am_short_delta": _clean_val(row.get("AM short Δ")),
                    })
                if push_records(table_name, records):
                    _CHECKED_EXISTING_DATES.add(f"{table_name}:{fin_current_date}")
                    status["cot_detailed_breakdown"] = f"pushed ({fin_current_date})"

    return status
