import pandas as pd
from datetime import date
from cot_fetcher import fetch_archive_week
from cot_parser import parse_report
from cot_calculator import compute_consolidated_table

# We want June 23 report (release June 26) and June 16 report (release June 22)
d1 = date(2026, 6, 26)
d2 = date(2026, 6, 22)

raw1 = fetch_archive_week(d1)
raw2 = fetch_archive_week(d2)

current = parse_report(raw1)
prev = parse_report(raw2)

df_calc = compute_consolidated_table(current, prev)
print("--- CALCULATED ---")
print(df_calc[["LF Net Pos", "LF Net %", "LF Δ"]].to_string())

