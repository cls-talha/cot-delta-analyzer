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
    
    # Reorder columns so Deltas are at the end
    base_cols = []
    delta_cols = []
    for col in df.columns:
        if "Δ" in col:
            delta_cols.append(col)
        else:
            base_cols.append(col)
            
    df = df[base_cols + delta_cols]
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
    
    # Reorder columns so Deltas are at the end
    base_cols = []
    delta_cols = []
    for col in df.columns:
        if "Δ" in col:
            delta_cols.append(col)
        else:
            base_cols.append(col)
            
    df = df[base_cols + delta_cols]
    return df
