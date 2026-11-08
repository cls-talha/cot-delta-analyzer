"""
Commodity Calculator module — computes CFTC Disaggregated Managed Money metrics for commodities.
"""

import pandas as pd
from typing import Dict, Optional, List
from commodity_config import COMMODITY_ORDER


def compute_commodity_table(
    current_data: Dict,
    previous_data: Optional[Dict],
) -> pd.DataFrame:
    """
    Build a DataFrame for commodities using CFTC Disaggregated Managed Money data.
    Columns:
      Commodity | Long | Short | Spread | Net | Long % | Short % | Open Int. | Δ Net | Δ Long | Δ Short
    """
    rows = []
    instruments = current_data.get("instruments", {})
    prev_instruments = previous_data.get("instruments", {}) if previous_data else {}

    for name in COMMODITY_ORDER:
        if name not in instruments:
            continue

        inst = instruments[name]
        long_pos = int(inst.get("mm_long", 0))
        short_pos = int(inst.get("mm_short", 0))
        spread_pos = int(inst.get("mm_spread", 0))
        open_interest = int(inst.get("open_interest", 0))

        net_pos = long_pos - short_pos
        total_ls = long_pos + short_pos

        if total_ls > 0:
            long_pct = round((long_pos / total_ls) * 100)
            short_pct = 100 - long_pct  # Ensure Long % + Short % == 100%
        else:
            long_pct = 0
            short_pct = 0

        # Delta Net calculation against previous report
        delta_net = None
        delta_long = None
        delta_short = None
        if name in prev_instruments:
            prev_inst = prev_instruments[name]
            prev_long = int(prev_inst.get("mm_long", 0))
            prev_short = int(prev_inst.get("mm_short", 0))
            prev_net = prev_long - prev_short
            delta_net = net_pos - prev_net
            delta_long = long_pos - prev_long
            delta_short = short_pos - prev_short

        row = {
            "Commodity": name,
            "Long": long_pos,
            "Short": short_pos,
            "Spread": spread_pos,
            "Net": net_pos,
            "Long %": long_pct,
            "Short %": short_pct,
            "Open Int.": open_interest,
            "Δ Net": delta_net,
            "Δ Long": delta_long,
            "Δ Short": delta_short,
        }
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("Commodity")
    ordered_cols = [
        "Long",
        "Short",
        "Spread",
        "Net",
        "Long %",
        "Short %",
        "Open Int.",
        "Δ Net",
        "Δ Long",
        "Δ Short",
    ]
    return df[ordered_cols]


def compute_commodity_historical_table(
    historical_data_list: List[Dict],
) -> pd.DataFrame:
    """
    Build a multi-week historical table for commodities using Disaggregated Managed Money format.
    MultiIndex: ["Commodity", "Report Date"]
    """
    rows = []

    for name in COMMODITY_ORDER:
        for idx, report_data in enumerate(historical_data_list):
            if (
                not report_data
                or "instruments" not in report_data
                or name not in report_data["instruments"]
            ):
                continue

            inst = report_data["instruments"][name]
            report_date = report_data.get("report_date", f"Week {-idx}")

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

            # Delta Net against consecutive prior report in historical_data_list
            delta_net = None
            delta_long = None
            delta_short = None
            if idx + 1 < len(historical_data_list):
                prev_report = historical_data_list[idx + 1]
                if (
                    prev_report
                    and "instruments" in prev_report
                    and name in prev_report["instruments"]
                ):
                    prev_inst = prev_report["instruments"][name]
                    prev_long = int(prev_inst.get("mm_long", 0))
                    prev_short = int(prev_inst.get("mm_short", 0))
                    prev_net = prev_long - prev_short
                    delta_net = net_pos - prev_net
                    delta_long = long_pos - prev_long
                    delta_short = short_pos - prev_short

            row = {
                "Commodity": name,
                "Report Date": report_date,
                "Long": long_pos,
                "Short": short_pos,
                "Spread": spread_pos,
                "Net": net_pos,
                "Long %": long_pct,
                "Short %": short_pct,
                "Open Int.": open_interest,
                "Δ Net": delta_net,
                "Δ Long": delta_long,
                "Δ Short": delta_short,
            }
            rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index(["Commodity", "Report Date"])
    ordered_cols = [
        "Long",
        "Short",
        "Spread",
        "Net",
        "Long %",
        "Short %",
        "Open Int.",
        "Δ Net",
        "Δ Long",
        "Δ Short",
    ]
    return df[ordered_cols]

