"""
Sync Historical COT Data to Supabase.

Reads cached weeks from 'data/cot_cache.json', calculates the 4 primary tables:
  1. Commodity COT (Disaggregated Managed Money) -> commodity_cot
  2. Current Week Overview                       -> cot_current_week_overview
  3. Leveraged Funds Breakdown                  -> cot_leveraged_funds_breakdown
  4. COT Detailed Breakdown                     -> cot_detailed_breakdown

Checks each week before pushing; skips any weeks already in Supabase.
Runs cleanly with pure Python (no external dependencies required besides requests).
Usage:
    python sync_supabase.py
"""

import json
import logging
import os
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_supabase")

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import contracts_to_billions
from commodity_config import COMMODITY_ORDER
from supabase_service import (
    is_supabase_configured,
    check_report_date_exists,
    push_records,
    get_secret,
)

INSTRUMENT_ORDER = [
    "USD (DXY)", "EUR", "GBP", "CAD", "AUD", "NZD", "CHF", "JPY",
]

CATEGORY_KEYS = {
    "Leveraged Funds": "leveraged_funds",
    "Asset Manager": "asset_manager",
    "Dealers": "dealer",
}

CATEGORY_SHORT = {
    "Leveraged Funds": "LF",
    "Asset Manager": "AM",
    "Dealers": "DI",
}


def compute_commodity_rows(curr_comm: dict, prev_comm: dict) -> list:
    """Calculate rows for commodity_cot table."""
    report_date = curr_comm.get("report_date")
    curr_insts = curr_comm.get("instruments", {})
    prev_insts = prev_comm.get("instruments", {}) if prev_comm else {}
    rows = []

    for name in COMMODITY_ORDER:
        if name not in curr_insts:
            continue
        inst = curr_insts[name]
        long_pos = int(inst.get("mm_long", 0))
        short_pos = int(inst.get("mm_short", 0))
        spread_pos = int(inst.get("mm_spread", 0))
        open_interest = int(inst.get("open_interest", 0))
        net_pos = long_pos - short_pos
        total_ls = long_pos + short_pos

        if total_ls > 0:
            long_pct = round((long_pos / total_ls) * 100)
            short_pct = 100 - long_pct
        else:
            long_pct = 0
            short_pct = 0

        delta_net = None
        delta_long = None
        delta_short = None
        if name in prev_insts:
            prev_inst = prev_insts[name]
            prev_long = int(prev_inst.get("mm_long", 0))
            prev_short = int(prev_inst.get("mm_short", 0))
            delta_long = int(long_pos - prev_long)
            delta_short = int(short_pos - prev_short)
            delta_net = int((long_pos - short_pos) - (prev_long - prev_short))

        rows.append({
            "report_date": report_date,
            "commodity": name,
            "long_pos": long_pos,
            "short_pos": short_pos,
            "spread": spread_pos,
            "net_pos": net_pos,
            "long_pct": float(long_pct),
            "short_pct": float(short_pct),
            "open_interest": open_interest,
            "delta_net": delta_net,
            "delta_long": delta_long,
            "delta_short": delta_short,
        })
    return rows


def compute_overview_rows(curr_fin: dict, prev_fin: dict) -> list:
    """Calculate rows for cot_current_week_overview table."""
    report_date = curr_fin.get("report_date")
    curr_insts = curr_fin.get("instruments", {})
    prev_insts = prev_fin.get("instruments", {}) if prev_fin else {}
    rows = []

    for name in INSTRUMENT_ORDER:
        if name not in curr_insts:
            continue
        inst = curr_insts[name]
        total_oi = inst.get("open_interest", 0)
        am = inst.get("asset_manager", {})
        lf = inst.get("leveraged_funds", {})

        am_long = am.get("long", 0)
        am_short = am.get("short", 0)
        lf_long = lf.get("long", 0)
        lf_short = lf.get("short", 0)

        total_long = int(lf_long + am_long)
        total_short = int(lf_short + am_short)

        row = {
            "report_date": report_date,
            "currency": name,
            "lf_am_long_positions": total_long,
            "lf_am_short_positions": total_short,
            "total_oi": int(total_oi),
        }

        # Net % deltas per category
        for cat_label, cat_key in CATEGORY_KEYS.items():
            cat_short = CATEGORY_SHORT[cat_label]
            cat_data = inst.get(cat_key, {})
            l = cat_data.get("long", 0)
            s = cat_data.get("short", 0)
            net = l - s
            tot = l + s
            net_pct = (net / tot * 100) if tot != 0 else 0.0

            delta = None
            if name in prev_insts:
                p_cat = prev_insts[name].get(cat_key, {})
                pl = p_cat.get("long", 0)
                ps = p_cat.get("short", 0)
                p_net = pl - ps
                p_tot = pl + ps
                p_pct = (p_net / p_tot * 100) if p_tot != 0 else 0.0
                delta = net_pct - p_pct

            row[f"{cat_short.lower()}_delta"] = round(delta, 2) if delta is not None else None

        if name in prev_insts:
            p_inst = prev_insts[name]
            p_am = p_inst.get("asset_manager", {})
            p_lf = p_inst.get("leveraged_funds", {})
            prev_total_long = p_lf.get("long", 0) + p_am.get("long", 0)
            prev_total_short = p_lf.get("short", 0) + p_am.get("short", 0)
            row["delta_long_positions"] = int(total_long - prev_total_long)
            row["delta_short_positions"] = int(total_short - prev_total_short)
        else:
            row["delta_long_positions"] = None
            row["delta_short_positions"] = None

        rows.append(row)
    return rows


def compute_lf_and_detailed_rows(curr_fin: dict, prev_fin: dict) -> tuple:
    """Calculate rows for cot_leveraged_funds_breakdown and cot_detailed_breakdown."""
    report_date = curr_fin.get("report_date")
    curr_insts = curr_fin.get("instruments", {})
    prev_insts = prev_fin.get("instruments", {}) if prev_fin else {}

    lf_rows = []
    det_rows = []

    for name in INSTRUMENT_ORDER:
        if name not in curr_insts:
            continue
        inst = curr_insts[name]
        total_oi = inst.get("open_interest", 0)
        lf = inst.get("leveraged_funds", {})
        am = inst.get("asset_manager", {})

        long_pos = lf.get("long", 0)
        short_pos = lf.get("short", 0)
        am_long = am.get("long", 0)
        am_short = am.get("short", 0)

        lf_total_oi = long_pos + short_pos
        net_pos = long_pos - short_pos
        net_pct = (net_pos / total_oi * 100) if total_oi != 0 else 0.0
        net_pct_lf = (net_pos / lf_total_oi * 100) if lf_total_oi != 0 else 0.0

        delta_lf_long = None
        delta_lf_short = None
        delta_am_long = None
        delta_am_short = None
        delta_tot_oi = None
        delta_lf_oi = None
        net_pct_lf_delta = None

        if name in prev_insts:
            p_inst = prev_insts[name]
            p_lf = p_inst.get("leveraged_funds", {})
            p_am = p_inst.get("asset_manager", {})
            p_long = p_lf.get("long", 0)
            p_short = p_lf.get("short", 0)
            p_lf_tot = p_long + p_short
            p_net = p_long - p_short
            p_pct_lf = (p_net / p_lf_tot * 100) if p_lf_tot != 0 else 0.0
            net_pct_lf_delta = round(net_pct_lf - p_pct_lf, 2)

            delta_tot_oi = int(total_oi - p_inst.get("open_interest", 0))
            delta_lf_oi = int(lf_total_oi - p_lf_tot)
            delta_lf_long = int(long_pos - p_long)
            delta_lf_short = int(short_pos - p_short)
            delta_am_long = int(am_long - p_am.get("long", 0))
            delta_am_short = int(am_short - p_am.get("short", 0))

        lf_rows.append({
            "report_date": report_date,
            "currency": name,
            "net_positions": int(net_pos),
            "net_percent": round(net_pct, 2),
            "net_percent_lf": round(net_pct_lf, 2),
            "net_pct_lf_delta": net_pct_lf_delta,
            "lf_long_delta": delta_lf_long,
            "lf_short_delta": delta_lf_short,
        })

        det_rows.append({
            "report_date": report_date,
            "currency": name,
            "delta_total_oi": delta_tot_oi,
            "delta_lf_oi": delta_lf_oi,
            "delta_lf_longs_usd_b": round(contracts_to_billions(name, delta_lf_long), 2) if delta_lf_long is not None else None,
            "delta_lf_shorts_usd_b": round(contracts_to_billions(name, delta_lf_short), 2) if delta_lf_short is not None else None,
            "delta_am_longs_usd_b": round(contracts_to_billions(name, delta_am_long), 2) if delta_am_long is not None else None,
            "delta_am_shorts_usd_b": round(contracts_to_billions(name, delta_am_short), 2) if delta_am_short is not None else None,
            "am_long_delta": delta_am_long,
            "am_short_delta": delta_am_short,
        })

    return lf_rows, det_rows


def sync_historical():
    if not is_supabase_configured():
        logger.error("Supabase is not configured. Please check SUPABASE_URL and SUPABASE_KEY in .streamlit/secrets.toml")
        return

    cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cot_cache.json")
    if not os.path.exists(cache_file):
        logger.error("Cache file not found at %s", cache_file)
        return

    with open(cache_file, "r") as f:
        cache = json.load(f)

    fin_keys = sorted([k for k in cache if not k.startswith("commodity_") and isinstance(cache[k], dict)], reverse=True)
    comm_keys = sorted([k for k in cache if k.startswith("commodity_2026") and isinstance(cache[k], dict)], reverse=True)

    logger.info("Found %d financial weeks and %d commodity weeks in cache.", len(fin_keys), len(comm_keys))

    # 1. Sync Commodity Weeks
    for i in range(len(comm_keys)):
        curr_comm = cache[comm_keys[i]]
        prev_comm = cache[comm_keys[i + 1]] if (i + 1) < len(comm_keys) else None
        comm_date = curr_comm.get("report_date")
        if not comm_date:
            continue

        if check_report_date_exists("commodity_cot", comm_date):
            logger.info("[commodity_cot] Week %s already exists. Skipping.", comm_date)
        else:
            rows = compute_commodity_rows(curr_comm, prev_comm)
            if push_records("commodity_cot", rows):
                logger.info("[commodity_cot] Pushed %d records for %s", len(rows), comm_date)

    # 2. Sync Financial Weeks (Overview, LF Breakdown, Detailed Breakdown)
    for i in range(len(fin_keys)):
        curr_fin = cache[fin_keys[i]]
        prev_fin = cache[fin_keys[i + 1]] if (i + 1) < len(fin_keys) else None
        fin_date = curr_fin.get("report_date")
        if not fin_date:
            continue

        # Overview
        if check_report_date_exists("cot_current_week_overview", fin_date):
            logger.info("[cot_current_week_overview] Week %s already exists. Skipping.", fin_date)
        else:
            rows = compute_overview_rows(curr_fin, prev_fin)
            if push_records("cot_current_week_overview", rows):
                logger.info("[cot_current_week_overview] Pushed %d records for %s", len(rows), fin_date)

        # LF Breakdown & Detailed Breakdown
        need_lf = not check_report_date_exists("cot_leveraged_funds_breakdown", fin_date)
        need_det = not check_report_date_exists("cot_detailed_breakdown", fin_date)

        if not need_lf and not need_det:
            logger.info("[lf & detailed] Week %s already exists. Skipping.", fin_date)
        else:
            lf_rows, det_rows = compute_lf_and_detailed_rows(curr_fin, prev_fin)
            if need_lf and push_records("cot_leveraged_funds_breakdown", lf_rows):
                logger.info("[cot_leveraged_funds_breakdown] Pushed %d records for %s", len(lf_rows), fin_date)
            if need_det and push_records("cot_detailed_breakdown", det_rows):
                logger.info("[cot_detailed_breakdown] Pushed %d records for %s", len(det_rows), fin_date)

    logger.info("Historical sync process completed!")


if __name__ == "__main__":
    sync_historical()
