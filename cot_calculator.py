"""
Calculator module — computes Net Positions, Net %, and deltas.

Consolidates all categories (LF, AM, DI) into a single table.
"""

import pandas as pd
from typing import Dict, Optional, List
from config import contracts_to_billions

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
    Build a consolidated DataFrame for the current week.
    Column order (strictly):
      LF Δ | AM Δ | DI Δ | LF+AM Long Positions | LF+AM Short Positions | Total OI | Δ Long Positions | Δ Short Positions
    - Long/Short Positions and their deltas are LF + AM combined (DI excluded).
    """
    rows = []
    instruments = current_data.get("instruments", {})

    for name in INSTRUMENT_ORDER:
        if name not in instruments:
            continue

        inst = instruments[name]
        total_oi = inst.get("open_interest", 0)

        # Per-category positions
        am = inst.get("asset_manager", {})
        lf = inst.get("leveraged_funds", {})

        am_long  = am.get("long", 0)
        am_short = am.get("short", 0)
        lf_long  = lf.get("long", 0)
        lf_short = lf.get("short", 0)

        # LF + AM combined long / short (DI excluded)
        total_long  = int(lf_long  + am_long)
        total_short = int(lf_short + am_short)

        row = {
            "Currency": name,
            "LF+AM Long Positions":  total_long,
            "LF+AM Short Positions": total_short,
            "Total OI":              int(total_oi),
        }

        # Net-% deltas per category (LF, AM, DI)
        for cat_label, cat_key in CATEGORY_KEYS.items():
            cat_short = CATEGORY_SHORT[cat_label]
            _, net_pct = _calculate_category_metrics(inst, cat_key)
            delta = None
            if previous_data and name in previous_data.get("instruments", {}):
                prev_inst = previous_data["instruments"][name]
                _, prev_net_pct = _calculate_category_metrics(prev_inst, cat_key)
                delta = net_pct - prev_net_pct
            row[f"{cat_short} Δ"] = round(delta, 2) if delta is not None else None

        # Combined LF+AM contract delta vs previous week
        if previous_data and name in previous_data.get("instruments", {}):
            prev_inst  = previous_data["instruments"][name]
            prev_am    = prev_inst.get("asset_manager", {})
            prev_lf    = prev_inst.get("leveraged_funds", {})
            prev_total_long  = prev_lf.get("long", 0)  + prev_am.get("long", 0)
            prev_total_short = prev_lf.get("short", 0) + prev_am.get("short", 0)
            row["Δ Long Positions"]  = int(total_long  - prev_total_long)
            row["Δ Short Positions"] = int(total_short - prev_total_short)
        else:
            row["Δ Long Positions"]  = None
            row["Δ Short Positions"] = None

        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("Currency")

    # Strict column order as requested
    ordered_cols = [
        "LF Δ", "AM Δ", "DI Δ",
        "LF+AM Long Positions", "LF+AM Short Positions", "Total OI",
        "Δ Long Positions", "Δ Short Positions",
    ]
    existing_cols = [c for c in ordered_cols if c in df.columns]
    return df[existing_cols]



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
    6. Δ LF Open Interest
    7. Δ Long Positions
    8. Δ Short Positions
    9. Δ LF Longs ($B)    ← NEW: week-over-week change in LF longs (billions USD)
    10. Δ LF Shorts ($B)   ← NEW: week-over-week change in LF shorts (billions USD)
    11. Δ AM Longs ($B)    ← NEW: week-over-week change in AM longs (billions USD)
    12. Δ AM Shorts ($B)   ← NEW: week-over-week change in AM shorts (billions USD)
    """
    rows = []
    instruments = current_data.get("instruments", {})

    for name in INSTRUMENT_ORDER:
        if name not in instruments:
            continue

        inst = instruments[name]
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

        row = {
            "Currency": name,
            "Net Positions": int(net_pos),
            "Net Percent": round(net_pct, 2),
            "Net Percent LF": round(net_pct_lf, 2),
            "Total Open Interest": int(total_oi),
            "Total LF Open Interest": int(lf_total_oi),
            "LF Long Positions": int(long_pos),
            "LF Short Positions": int(short_pos),
        }

        if previous_data and name in previous_data.get("instruments", {}):
            prev_inst = previous_data["instruments"][name]
            prev_total_oi = prev_inst.get("open_interest", 0)
            prev_lf = prev_inst.get("leveraged_funds", {})
            prev_am = prev_inst.get("asset_manager", {})
            prev_long = prev_lf.get("long", 0)
            prev_short = prev_lf.get("short", 0)
            prev_am_long = prev_am.get("long", 0)
            prev_am_short = prev_am.get("short", 0)
            prev_lf_total_oi = prev_long + prev_short
            prev_net_pos = prev_long - prev_short
            prev_net_pct_lf = (prev_net_pos / prev_lf_total_oi * 100) if prev_lf_total_oi != 0 else 0.0

            # Delta contract values (week-over-week change)
            delta_lf_long_contracts = long_pos - prev_long
            delta_lf_short_contracts = short_pos - prev_short
            delta_am_long_contracts = am_long - prev_am_long
            delta_am_short_contracts = am_short - prev_am_short

            row["Net % LF Δ"] = round(net_pct_lf - prev_net_pct_lf, 2)
            row["Δ Total Open Interest"] = int(total_oi - prev_total_oi)
            row["Δ LF Open Interest"] = int(lf_total_oi - prev_lf_total_oi)
            row["Δ Long Positions"] = int(delta_lf_long_contracts + delta_am_long_contracts)
            row["Δ Short Positions"] = int(delta_lf_short_contracts + delta_am_short_contracts)

            row["LF longs Δ"] = int(delta_lf_long_contracts)
            row["LF short Δ"] = int(delta_lf_short_contracts)
            row["AM long Δ"] = int(delta_am_long_contracts)
            row["AM short Δ"] = int(delta_am_short_contracts)

            row["Δ LF Longs ($B)"] = round(contracts_to_billions(name, delta_lf_long_contracts), 2)
            row["Δ LF Shorts ($B)"] = round(contracts_to_billions(name, delta_lf_short_contracts), 2)
            row["Δ AM Longs ($B)"] = round(contracts_to_billions(name, delta_am_long_contracts), 2)
            row["Δ AM Shorts ($B)"] = round(contracts_to_billions(name, delta_am_short_contracts), 2)

        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("Currency")

    desired_order = [
        "Net Positions",
        "Net Percent",
        "Net Percent LF",
        "Net % LF Δ",
        "Total Open Interest",
        "Total LF Open Interest",
        "Long Positions",
        "Short Positions",
        "LF longs Δ",
        "LF short Δ",
        "AM long Δ",
        "AM short Δ",
        "Δ Total Open Interest",
        "Δ LF Open Interest",
        "Δ Long Positions",
        "Δ Short Positions",
        "Δ LF Longs ($B)",
        "Δ LF Shorts ($B)",
        "Δ AM Longs ($B)",
        "Δ AM Shorts ($B)",
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

            am = inst.get("asset_manager", {})
            am_long = am.get("long", 0)
            am_short = am.get("short", 0)

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
                "LF Long Positions": int(long_pos),
                "LF Short Positions": int(short_pos),
            }

            if idx + 1 < len(historical_data_list):
                prev_report = historical_data_list[idx + 1]
                if prev_report and "instruments" in prev_report and name in prev_report["instruments"]:
                    prev_inst = prev_report["instruments"][name]
                    prev_total_oi = prev_inst.get("open_interest", 0)
                    prev_lf = prev_inst.get("leveraged_funds", {})
                    prev_am = prev_inst.get("asset_manager", {})
                    prev_long = prev_lf.get("long", 0)
                    prev_short = prev_lf.get("short", 0)
                    prev_am_long = prev_am.get("long", 0)
                    prev_am_short = prev_am.get("short", 0)
                    prev_lf_total_oi = prev_long + prev_short
                    prev_net_pos = prev_long - prev_short
                    prev_net_pct_lf = (prev_net_pos / prev_lf_total_oi * 100) if prev_lf_total_oi != 0 else 0.0

                    # Delta contract values (week-over-week change)
                    delta_lf_long_contracts = long_pos - prev_long
                    delta_lf_short_contracts = short_pos - prev_short
                    delta_am_long_contracts = am_long - prev_am_long
                    delta_am_short_contracts = am_short - prev_am_short

                    row["Net % LF Δ"] = round(net_pct_lf - prev_net_pct_lf, 2)
                    row["Δ Total Open Interest"] = int(total_oi - prev_total_oi)
                    row["Δ LF Open Interest"] = int(lf_total_oi - prev_lf_total_oi)
                    row["Δ Long Positions"] = int(delta_lf_long_contracts + delta_am_long_contracts)
                    row["Δ Short Positions"] = int(delta_lf_short_contracts + delta_am_short_contracts)

                    row["LF longs Δ"] = int(delta_lf_long_contracts)
                    row["LF short Δ"] = int(delta_lf_short_contracts)
                    row["AM long Δ"] = int(delta_am_long_contracts)
                    row["AM short Δ"] = int(delta_am_short_contracts)

                    row["Δ LF Longs ($B)"] = round(contracts_to_billions(name, delta_lf_long_contracts), 2)
                    row["Δ LF Shorts ($B)"] = round(contracts_to_billions(name, delta_lf_short_contracts), 2)
                    row["Δ AM Longs ($B)"] = round(contracts_to_billions(name, delta_am_long_contracts), 2)
                    row["Δ AM Shorts ($B)"] = round(contracts_to_billions(name, delta_am_short_contracts), 2)

            rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index(["Currency", "Report Date"])

    desired_order = [
        "Net Positions",
        "Net Percent",
        "Net Percent LF",
        "Net % LF Δ",
        "Total Open Interest",
        "Total LF Open Interest",
        "Long Positions",
        "Short Positions",
        "LF longs Δ",
        "LF short Δ",
        "AM long Δ",
        "AM short Δ",
        "Δ Total Open Interest",
        "Δ LF Open Interest",
        "Δ Long Positions",
        "Δ Short Positions",
        "Δ LF Longs ($B)",
        "Δ LF Shorts ($B)",
        "Δ AM Longs ($B)",
        "Δ AM Shorts ($B)",
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


def calculate_lf_composite_index(
    df_lf_detail: pd.DataFrame,
    weights: dict = {"strength": 0.60, "delta": 0.25, "oi_momentum": 0.15}
):
    """
    Calculate LF Composite Strength Index for currencies and currency pairs.
    
    Weights:
    - LF Strength: 0.60 (Net Percent LF percentile)
    - LF Delta / Momentum: 0.25 (Net % LF Δ percentile)
    - LF OI Momentum: 0.15 (Δ LF Open Interest / Previous LF Open Interest * 100 percentile)
    
    Percentile methodology:
    percentile = rank / (N - 1) * 100
    where N = number of valid currencies (strongest = 100, weakest = 0, average rank for ties).
    If N == 1, rank/percentile is 100.
    
    Returns:
    - curr_df: DataFrame with columns [Currency, LF Strength, LF Delta, LF OI Momentum, Composite Score]
    - pairs_list: List of tuples (pair_symbol, pair_score) sorted descending by pair_score.
    """
    if df_lf_detail.empty:
        return pd.DataFrame(), []

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

    raw_rows = []
    for idx, row in df_lf_detail.iterrows():
        ticker = curr_map.get(str(idx), str(idx).split()[0])
        
        net_pct_lf = row.get("Net Percent LF", None)
        net_pct_lf_delta = row.get("Net % LF Δ", None)
        
        total_lf_oi = row.get("Total LF Open Interest", None)
        delta_lf_oi = row.get("Δ LF Open Interest", None)
        
        oi_momentum_pct = None
        if pd.notna(total_lf_oi) and pd.notna(delta_lf_oi):
            prev_lf_oi = float(total_lf_oi) - float(delta_lf_oi)
            if prev_lf_oi > 0:
                oi_momentum_pct = (float(delta_lf_oi) / prev_lf_oi) * 100.0

        raw_rows.append({
            "Currency": ticker,
            "net_pct_lf": float(net_pct_lf) if pd.notna(net_pct_lf) else None,
            "net_pct_lf_delta": float(net_pct_lf_delta) if pd.notna(net_pct_lf_delta) else None,
            "oi_momentum_pct": oi_momentum_pct,
        })

    df_comp = pd.DataFrame(raw_rows)

    def calc_percentile(series: pd.Series) -> pd.Series:
        valid_s = series.dropna()
        N = len(valid_s)
        if N == 0:
            return pd.Series(index=series.index, dtype=float)
        if N == 1:
            return pd.Series(100.0, index=valid_s.index).reindex(series.index)
        
        ranks = valid_s.rank(ascending=True, method="average") - 1.0
        percentiles = (ranks / (N - 1)) * 100.0
        return percentiles.reindex(series.index)

    df_comp["lf_strength_pct"] = calc_percentile(df_comp["net_pct_lf"])
    df_comp["lf_delta_pct"] = calc_percentile(df_comp["net_pct_lf_delta"])
    df_comp["lf_oi_mom_pct"] = calc_percentile(df_comp["oi_momentum_pct"])

    w_str = weights.get("strength", 0.60)
    w_del = weights.get("delta", 0.25)
    w_oi = weights.get("oi_momentum", 0.15)

    composite_scores = []
    for _, r in df_comp.iterrows():
        s = r["lf_strength_pct"]
        d = r["lf_delta_pct"]
        o = r["lf_oi_mom_pct"]
        
        # Calculate score using available valid component percentiles
        w_sum = 0.0
        val_sum = 0.0
        if pd.notna(s):
            w_sum += w_str
            val_sum += w_str * s
        if pd.notna(d):
            w_sum += w_del
            val_sum += w_del * d
        if pd.notna(o):
            w_sum += w_oi
            val_sum += w_oi * o

        score = (val_sum / w_sum) if w_sum > 0 else None
        composite_scores.append(score)

    df_comp["Composite Score"] = composite_scores

    # Build display dataframe
    df_display = pd.DataFrame({
        "Currency": df_comp["Currency"],
        "LF Strength": df_comp["lf_strength_pct"].round(2),
        "LF Delta": df_comp["lf_delta_pct"].round(2),
        "LF OI Momentum": df_comp["lf_oi_mom_pct"].round(2),
        "Composite Score": df_comp["Composite Score"].round(2),
    }).sort_values(by="Composite Score", ascending=False).reset_index(drop=True)

    # Calculate 28 Currency Pairs Composite Strength
    scores_dict = dict(zip(df_display["Currency"], df_display["Composite Score"]))

    pairs_def = [
        ("AUD", "NZD"), ("GBP", "NZD"), ("AUD", "CAD"), ("GBP", "CAD"), ("USD", "CAD"), ("AUD", "CHF"), ("AUD", "JPY"),
        ("GBP", "CHF"), ("GBP", "JPY"), ("EUR", "NZD"), ("EUR", "CAD"), ("USD", "CHF"), ("USD", "JPY"), ("AUD", "USD"),
        ("GBP", "USD"), ("EUR", "CHF"), ("EUR", "JPY"), ("CHF", "JPY"), ("GBP", "AUD"), ("NZD", "CAD"), ("EUR", "USD"),
        ("CAD", "CHF"), ("CAD", "JPY"), ("NZD", "CHF"), ("NZD", "JPY"), ("EUR", "GBP"), ("EUR", "AUD"), ("NZD", "USD"),
    ]

    pairs_results = []
    for base, quote in pairs_def:
        if base in scores_dict and quote in scores_dict and pd.notna(scores_dict[base]) and pd.notna(scores_dict[quote]):
            p_score = scores_dict[base] - scores_dict[quote]
            pair_symbol = f"{base}{quote}"
            pairs_results.append((pair_symbol, round(p_score, 2)))

    pairs_results.sort(key=lambda x: x[1], reverse=True)

    return df_display, pairs_results



