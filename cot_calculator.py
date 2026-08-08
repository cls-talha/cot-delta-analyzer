"""
Calculator module — computes Net Positions, Net %, and deltas.

Consolidates all categories (LF, AM, DI) into a single table.
"""

import pandas as pd
from typing import Dict, Optional, List

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

INSTRUMENT_ORDER = [
    "USD (DXY)", "EUR", "GBP", "CAD", "AUD", "NZD", "CHF", "JPY",
]

def _calculate_category_metrics(inst_data: dict, cat_key: str):
    """Calculate Net Positions and Net % for a single category."""
    oi = inst_data["open_interest"]
    cat = inst_data[cat_key]
    long_val = cat["long"]
    short_val = cat["short"]
    
    net = long_val - short_val
    total_ls = long_val + short_val
    net_pct_cat = (net / total_ls * 100) if total_ls != 0 else 0.0
    
    return int(net), net_pct_cat


def compute_consolidated_table(
    current_data: Dict,
    previous_data: Optional[Dict],
) -> pd.DataFrame:
    """
    Build a consolidated DataFrame for the current week containing
    all categories (LF, AM, DI) and their deltas.
    """
    rows = []
    instruments = current_data.get("instruments", {})

    for name in INSTRUMENT_ORDER:
        if name not in instruments:
            continue

        inst = instruments[name]
        
        row = {"Currency": name}
        
        # Calculate for each category
        for cat_label, cat_key in CATEGORY_KEYS.items():
            cat_short = CATEGORY_SHORT[cat_label]
            net, net_pct = _calculate_category_metrics(inst, cat_key)
            
            row[f"{cat_short} Net Pos"] = net
            row[f"{cat_short} Net %"] = round(net_pct, 2)
            
            # Calculate delta if previous data exists
            delta = None
            if previous_data and name in previous_data.get("instruments", {}):
                prev_inst = previous_data["instruments"][name]
                _, prev_net_pct = _calculate_category_metrics(prev_inst, cat_key)
                delta = net_pct - prev_net_pct
            
            # We'll temporarily store delta, but we want them grouped at the end
            row[f"{cat_short} Δ"] = round(delta, 2) if delta is not None else None

        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.set_index("Currency")
    
    # Reorder columns so Deltas are right in front of currency / first columns
    delta_cols = []
    base_cols = []
    for col in df.columns:
        if "Δ" in col:
            delta_cols.append(col)
        else:
            base_cols.append(col)
            
    df = df[delta_cols + base_cols]
    return df


def compute_historical_table(historical_data_list: List[Dict]) -> pd.DataFrame:
    """
    Build a multi-week history table with deltas.
     historical_data_list should be ordered from most recent to oldest.
    """
    rows = []
    
    for name in INSTRUMENT_ORDER:
        for idx, report_data in enumerate(historical_data_list):
            if not report_data or "instruments" not in report_data or name not in report_data["instruments"]:
                continue
                
            inst = report_data["instruments"][name]
            report_date = report_data.get("report_date", f"Week {-idx}")
            
            row = {
                "Currency": name,
                "Report Date": report_date,
            }
            
            # Get previous report data if available (which is the next item in the list)
            prev_inst = None
            if idx + 1 < len(historical_data_list):
                prev_report = historical_data_list[idx + 1]
                if prev_report and "instruments" in prev_report and name in prev_report["instruments"]:
                    prev_inst = prev_report["instruments"][name]
            
            for cat_label, cat_key in CATEGORY_KEYS.items():
                cat_short = CATEGORY_SHORT[cat_label]
                net, net_pct = _calculate_category_metrics(inst, cat_key)
                
                row[f"{cat_short} Net Pos"] = net
                row[f"{cat_short} Net %"] = round(net_pct, 2)
                
                # Delta
                delta = None
                if prev_inst:
                    _, prev_net_pct = _calculate_category_metrics(prev_inst, cat_key)
                    delta = net_pct - prev_net_pct
                
                row[f"{cat_short} Δ"] = round(delta, 2) if delta is not None else None
                
            rows.append(row)
            
    if not rows:
        return pd.DataFrame()
        
    df = pd.DataFrame(rows)
    # Set multi-index for better presentation
    df = df.set_index(["Currency", "Report Date"])
    
    # Reorder columns so Deltas are right in front of currency / first columns
    delta_cols = []
    base_cols = []
    for col in df.columns:
        if "Δ" in col:
            delta_cols.append(col)
        else:
            base_cols.append(col)
            
    df = df[delta_cols + base_cols]
    return df


def compute_lf_detail_table(
    current_data: Dict,
    previous_data: Optional[Dict],
) -> pd.DataFrame:
    """
    Build detailed Leveraged Funds DataFrame containing OI, position breakdowns, and deltas.
    Columns follow user's exact ordering requirement:
    1. Net Positions
    2. Net Percent
    3. Net Percent LF
    4. Net % LF Δ
    5. Δ Total Open Interest
    6. Total Open Interest
    7. Δ LF Open Interest
    8. Total LF Open Interest
    9. Long Positions
    10. Short Positions
    11. Δ Long Positions
    12. Δ Short Positions
    """
    rows = []
    instruments = current_data.get("instruments", {})

    for name in INSTRUMENT_ORDER:
        if name not in instruments:
            continue

        inst = instruments[name]
        total_oi = inst.get("open_interest", 0)
        lf = inst.get("leveraged_funds", {})
        long_pos = lf.get("long", 0)
        short_pos = lf.get("short", 0)
        
        lf_total_oi = long_pos + short_pos
        net_pos = long_pos - short_pos
        net_pct = (net_pos / total_oi * 100) if total_oi != 0 else 0.0
        net_pct_lf = (net_pos / lf_total_oi * 100) if lf_total_oi != 0 else 0.0

        row = {
            "Currency": name,
            "Net Positions": int(net_pos),
            "Net Percent": round(net_pct, 2),
            "Net Percent LF": round(net_pct_lf, 2),
            "Total Open Interest": int(total_oi),
            "Total LF Open Interest": int(lf_total_oi),
            "Long Positions": int(long_pos),
            "Short Positions": int(short_pos),
        }

        if previous_data and name in previous_data.get("instruments", {}):
            prev_inst = previous_data["instruments"][name]
            prev_total_oi = prev_inst.get("open_interest", 0)
            prev_lf = prev_inst.get("leveraged_funds", {})
            prev_long = prev_lf.get("long", 0)
            prev_short = prev_lf.get("short", 0)
            prev_lf_total_oi = prev_long + prev_short
            prev_net_pos = prev_long - prev_short
            prev_net_pct_lf = (prev_net_pos / prev_lf_total_oi * 100) if prev_lf_total_oi != 0 else 0.0

            row["Net % LF Δ"] = round(net_pct_lf - prev_net_pct_lf, 2)
            row["Δ Total Open Interest"] = int(total_oi - prev_total_oi)
            row["Δ LF Open Interest"] = int(lf_total_oi - prev_lf_total_oi)
            row["Δ Long Positions"] = int(long_pos - prev_long)
            row["Δ Short Positions"] = int(short_pos - prev_short)

        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("Currency")

    desired_order = [
        "Net Positions",
        "Net Percent",
        "Net Percent LF",
        "Net % LF Δ",
        "Δ Total Open Interest",
        "Δ LF Open Interest",
        "Δ Long Positions",
        "Δ Short Positions",
        "Total Open Interest",
        "Total LF Open Interest",
        "Long Positions",
        "Short Positions",
    ]

    existing_cols = [c for c in desired_order if c in df.columns]
    return df[existing_cols]


def compute_lf_detail_historical_table(historical_data_list: List[Dict]) -> pd.DataFrame:
    """
    Build multi-week history table for Leveraged Funds detail with deltas.
    """
    rows = []

    for name in INSTRUMENT_ORDER:
        for idx, report_data in enumerate(historical_data_list):
            if not report_data or "instruments" not in report_data or name not in report_data["instruments"]:
                continue

            inst = report_data["instruments"][name]
            report_date = report_data.get("report_date", f"Week {-idx}")

            total_oi = inst.get("open_interest", 0)
            lf = inst.get("leveraged_funds", {})
            long_pos = lf.get("long", 0)
            short_pos = lf.get("short", 0)

            lf_total_oi = long_pos + short_pos
            net_pos = long_pos - short_pos
            net_pct = (net_pos / total_oi * 100) if total_oi != 0 else 0.0
            net_pct_lf = (net_pos / lf_total_oi * 100) if lf_total_oi != 0 else 0.0

            row = {
                "Currency": name,
                "Report Date": report_date,
                "Net Positions": int(net_pos),
                "Net Percent": round(net_pct, 2),
                "Net Percent LF": round(net_pct_lf, 2),
                "Total Open Interest": int(total_oi),
                "Total LF Open Interest": int(lf_total_oi),
                "Long Positions": int(long_pos),
                "Short Positions": int(short_pos),
            }

            if idx + 1 < len(historical_data_list):
                prev_report = historical_data_list[idx + 1]
                if prev_report and "instruments" in prev_report and name in prev_report["instruments"]:
                    prev_inst = prev_report["instruments"][name]
                    prev_total_oi = prev_inst.get("open_interest", 0)
                    prev_lf = prev_inst.get("leveraged_funds", {})
                    prev_long = prev_lf.get("long", 0)
                    prev_short = prev_lf.get("short", 0)
                    prev_lf_total_oi = prev_long + prev_short
                    prev_net_pos = prev_long - prev_short
                    prev_net_pct_lf = (prev_net_pos / prev_lf_total_oi * 100) if prev_lf_total_oi != 0 else 0.0

                    row["Net % LF Δ"] = round(net_pct_lf - prev_net_pct_lf, 2)
                    row["Δ Total Open Interest"] = int(total_oi - prev_total_oi)
                    row["Δ LF Open Interest"] = int(lf_total_oi - prev_lf_total_oi)
                    row["Δ Long Positions"] = int(long_pos - prev_long)
                    row["Δ Short Positions"] = int(short_pos - prev_short)

            rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index(["Currency", "Report Date"])

    desired_order = [
        "Net Positions",
        "Net Percent",
        "Net Percent LF",
        "Net % LF Δ",
        "Δ Total Open Interest",
        "Δ LF Open Interest",
        "Δ Long Positions",
        "Δ Short Positions",
        "Total Open Interest",
        "Total LF Open Interest",
        "Long Positions",
        "Short Positions",
    ]

    existing_cols = [c for c in desired_order if c in df.columns]
    return df[existing_cols]


def calculate_lf_strength_index(df_lf_detail: pd.DataFrame) -> List[tuple]:
    """
    Calculate the LF Strength Index for all 28 currency pairs based on Leveraged Funds Net Percent LF ('Net Percent LF').
    Returns a list of tuples: (pair_name, index_val), sorted descending by index_val.
    
    Formula matching Excel Terminal Sheet:
    Strength Index = (Base_Net_Percent_LF - Quote_Net_Percent_LF) / 2
    
    Currencies involved: AUD, NZD, GBP, CAD, USD, CHF, JPY, EUR
    """
    if df_lf_detail.empty or "Net Percent LF" not in df_lf_detail.columns:
        return []
    
    # Map currency raw name to clean ticker name
    curr_map = {
        "USD (DXY)": "USD",
        "USD": "USD",
        "EUR": "EUR",
        "GBP": "GBP",
        "CAD": "CAD",
        "AUD": "AUD",
        "NZD": "NZD",
        "CHF": "CHF",
        "JPY": "JPY"
    }
    
    # Extract Net Percent LF values keyed by ticker name
    lf_pcts = {}
    for idx, row in df_lf_detail.iterrows():
        ticker = curr_map.get(str(idx), str(idx).split()[0])
        val = row["Net Percent LF"]
        if pd.notna(val):
            lf_pcts[ticker] = float(val)

    # Standard Forex Pairs definition list (28 pairs)
    pairs_def = [
        ("AUD", "NZD"), ("GBP", "NZD"), ("AUD", "CAD"), ("GBP", "CAD"), ("USD", "CAD"), ("AUD", "CHF"), ("AUD", "JPY"),
        ("GBP", "CHF"), ("GBP", "JPY"), ("EUR", "NZD"), ("EUR", "CAD"), ("USD", "CHF"), ("USD", "JPY"), ("AUD", "USD"),
        ("GBP", "USD"), ("EUR", "CHF"), ("EUR", "JPY"), ("CHF", "JPY"), ("GBP", "AUD"), ("NZD", "CAD"), ("EUR", "USD"),
        ("CAD", "CHF"), ("CAD", "JPY"), ("NZD", "CHF"), ("NZD", "JPY"), ("EUR", "GBP"), ("EUR", "AUD"), ("NZD", "USD"),
    ]

    results = []
    for base, quote in pairs_def:
        if base in lf_pcts and quote in lf_pcts:
            strength_diff = (lf_pcts[base] - lf_pcts[quote]) / 2.0
            pair_symbol = f"{base}{quote}"
            results.append((pair_symbol, round(strength_diff, 2)))
            
    # Sort by strength_diff descending
    results.sort(key=lambda x: x[1], reverse=True)
    return results


