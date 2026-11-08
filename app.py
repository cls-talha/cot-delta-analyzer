"""
COT Analyzer Dashboard — Streamlit Application.

Displays CFTC Commitments of Traders data for Leveraged Funds,
Asset Managers, and Dealers across major currencies and indices.
Single-page layout with Plotly graphs and historical tables.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
import plotly.express as px
import json
import os
from typing import Optional

from cot_fetcher import fetch_current_week, fetch_archive_week, get_recent_release_dates
from cot_parser import parse_report
from cot_calculator import (
    compute_consolidated_table,
    compute_historical_table,
    compute_lf_detail_table,
    compute_lf_detail_historical_table,
    calculate_lf_strength_index,
    calculate_lf_composite_index,
    CATEGORY_SHORT,
)
from commodity_fetcher import (
    fetch_commodity_current_week,
    fetch_commodity_archive_week,
)
from commodity_parser import parse_commodity_report
from commodity_calculator import (
    compute_commodity_table,
    compute_commodity_historical_table,
)
import warnings

# Suppress standard Python/Streamlit warnings
warnings.filterwarnings("ignore", category=UserWarning, module="streamlit")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="streamlit")

# Suppress Streamlit UI-specific warning elements
st.set_option("client.showErrorDetails", False)
st.set_option("global.developmentMode", False)
# ──────────────────────────────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="COT Analyzer Dashboard",
    page_icon=":material/bar_chart:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ──────────────────────────────────────────────────────────────────────
# Custom CSS — premium dark styling
# ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* Global */
.stApp {
    font-family: 'Inter', sans-serif;
}

/* Center & constrain content on wide monitors */
.block-container {
    max-width: 1400px !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
    margin-left: auto !important;
    margin-right: auto !important;
}

/* Header area */
.main-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    padding: 1.5rem 2rem;
    border-radius: 12px;
    margin-bottom: 1rem;
    border: 1px solid rgba(255,255,255,0.06);
    box-shadow: 0 4px 24px rgba(0,0,0,0.3);
}
.main-header h1 {
    color: #e0e7ff;
    font-weight: 700;
    font-size: 2rem;
    margin: 0 0 0.3rem 0;
    letter-spacing: -0.5px;
}
.main-header .subtitle {
    color: #94a3b8;
    font-size: 1rem;
    font-weight: 400;
}

/* Date badges */
.date-badge {
    display: inline-block;
    background: rgba(99,102,241,0.15);
    border: 1px solid rgba(99,102,241,0.3);
    color: #a5b4fc;
    padding: 0.4rem 1rem;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 600;
}

/* Table styling */
.dataframe {
    font-family: 'Inter', monospace !important;
    font-size: 0.85rem !important;
}
.dataframe th {
    background: rgba(30,30,60,0.8) !important;
    color: #a5b4fc !important;
    font-weight: 600 !important;
    text-align: center !important;
    padding: 0.4rem 0.35rem !important;
    border-bottom: 2px solid rgba(99,102,241,0.3) !important;
    font-size: 0.8rem !important;
    white-space: nowrap !important;
}
.dataframe td {
    text-align: center !important;
    padding: 0.35rem 0.3rem !important;
    border-bottom: 1px solid rgba(255,255,255,0.04) !important;
    white-space: nowrap !important;
}
.dataframe tr:hover td {
    background: rgba(99,102,241,0.1) !important;
}

/* Footer */
.footer {
    text-align: center;
    color: #64748b;
    font-size: 0.75rem;
    padding: 1.5rem 0;
    border-top: 1px solid rgba(255,255,255,0.05);
    margin-top: 2rem;
}
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────
# Data loading with caching
# ──────────────────────────────────────────────────────────────────────
CACHE_FILE = "data/cot_cache.json"


def _read_cache() -> dict:
    """Read the full disk cache file and return it as a dict."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Cache] Error reading cache file: {e}")
    return {}


def _write_cache(cache: dict):
    """Write the full disk cache dict to file."""
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"[Cache] Error writing cache file: {e}")


def get_cached_report(date_str: str) -> Optional[dict]:
    """Retrieve COT (forex) report from disk cache."""
    return _read_cache().get(date_str)


def _is_valid_cot(parsed: Optional[dict]) -> bool:
    """Return True only if the parsed COT result contains real data."""
    if not parsed:
        return False
    if not parsed.get("report_date"):
        return False
    if not parsed.get("instruments"):
        return False
    return True


def _is_valid_html(raw: Optional[str]) -> bool:
    """
    Return True only if raw HTML looks like a real CFTC report page.
    Cloudflare challenge pages contain 'Just a moment' and are small (<15 KB).
    """
    if not raw:
        return False
    if "Just a moment" in raw:
        return False
    if len(raw) < 5_000:
        return False
    return True


def save_cached_report(date_str: str, report_data: dict):
    """Save COT (forex) report to disk cache only if it contains valid data."""
    if not _is_valid_cot(report_data):
        print(f"[Cache] Skipping save for {date_str}: parsed data is empty or invalid.")
        return
    cache = _read_cache()
    cache[date_str] = report_data
    _write_cache(cache)


def get_cached_commodity_report(date_str: str) -> Optional[dict]:
    """Retrieve commodity report (parsed dict) from disk cache."""
    cache = _read_cache()
    return cache.get(f"commodity_{date_str}")


def save_cached_commodity_report(date_str: str, parsed: dict):
    """Save parsed commodity report to disk cache if it contains valid data."""
    if not parsed or not parsed.get("report_date") or not parsed.get("instruments"):
        print(f"[Cache] Skipping commodity save for {date_str}: empty or invalid.")
        return
    cache = _read_cache()
    cache[f"commodity_{date_str}"] = parsed
    _write_cache(cache)


@st.cache_data(ttl=3600, show_spinner=False)
def load_week_data(release_date_str: str, is_latest: bool = False) -> Optional[dict]:
    """
    Load COT (forex/financial) data for a specific release date via Socrata API.

    Strategy:
      1. Check disk cache — if found, return immediately.
      2. Fetch records from Socrata.
      3. Parse, save to disk cache, and return.
    """
    # 1. Disk cache hit
    cached = get_cached_report(release_date_str)
    if cached and _is_valid_cot(cached):
        return cached

    # 2. Fetch from Socrata
    if is_latest:
        records = fetch_current_week()
        if not records:
            # Fallback: fetch by specific release date
            parts = release_date_str.split("-")
            d = date(int(parts[0]), int(parts[1]), int(parts[2]))
            records = fetch_archive_week(d)
    else:
        parts = release_date_str.split("-")
        d = date(int(parts[0]), int(parts[1]), int(parts[2]))
        records = fetch_archive_week(d)

    if not records:
        return None

    parsed = parse_report(records)
    if parsed:
        save_cached_report(release_date_str, parsed)
    return parsed


@st.cache_data(ttl=3600, show_spinner=False)
def load_commodity_week_data(release_date_str: str, is_latest: bool = False) -> Optional[dict]:
    """
    Load commodity COT data for a specific release date via Socrata API.

    Strategy:
      1. Check disk cache — if found, return immediately.
      2. Fetch records from Socrata.
      3. Parse, save to disk cache, and return.
    """
    # 1. Disk cache hit
    cached = get_cached_commodity_report(release_date_str)
    if cached and cached.get("report_date"):
        return cached

    # 2. Fetch from Socrata
    if is_latest:
        records = fetch_commodity_current_week()
        if not records:
            parts = release_date_str.split("-")
            d = date(int(parts[0]), int(parts[1]), int(parts[2]))
            records = fetch_commodity_archive_week(d)
    else:
        parts = release_date_str.split("-")
        d = date(int(parts[0]), int(parts[1]), int(parts[2]))
        records = fetch_commodity_archive_week(d)

    if not records:
        return None

    parsed = parse_commodity_report(records)
    if parsed and parsed.get("report_date"):
        save_cached_commodity_report(release_date_str, parsed)
    return parsed


def style_delta(val):
    """Apply red/green styling to delta values with subtle background highlights."""
    if pd.isna(val) or val is None:
        return "color: #64748b"
    if val > 0:
        return "color: #4ade80; font-weight: 600; background-color: rgba(74, 222, 128, 0.1);"
    elif val < 0:
        return "color: #f87171; font-weight: 600; background-color: rgba(248, 113, 113, 0.1);"
    return "color: #94a3b8"


def format_commodity_dataframe(df: pd.DataFrame):
    """Apply formatting to the Commodity Legacy COT DataFrame."""
    format_dict = {
        "Long": "{:,.0f}",
        "Short": "{:,.0f}",
        "Spread": "{:,.0f}",
        "Net": "{:,.0f}",
        "Long %": "{:.0f}%",
        "Short %": "{:.0f}%",
        "Open Int.": "{:,.0f}",
        "Δ Net": "{:+,.0f}",
        "Δ Long": "{:+,.0f}",
        "Δ Short": "{:+,.0f}",
    }

    styled = df.style.format(format_dict, na_rep="—")
    
    delta_cols = [c for c in ["Δ Net", "Δ Long", "Δ Short"] if c in df.columns]

    if delta_cols:
        if hasattr(styled, "map"):
            styled = styled.map(style_delta, subset=delta_cols)
        else:
            styled = styled.applymap(style_delta, subset=delta_cols)

    styled = styled.set_properties(**{
        "text-align": "center",
        "font-size": "0.85rem",
    })
    return styled


def format_consolidated_dataframe(df: pd.DataFrame):
    """Apply formatting to the consolidated DataFrame."""
    format_dict = {}
    delta_pct_cols = []   # LF Δ, AM Δ, DI Δ  — net-% deltas
    delta_pos_cols = []   # Δ Long Positions, Δ Short Positions — signed contracts

    for col in df.columns:
        if col in ("LF Δ", "AM Δ", "DI Δ"):
            format_dict[col] = "{:+.2f}%"
            delta_pct_cols.append(col)
        elif col in ("Δ Long Positions", "Δ Short Positions"):
            format_dict[col] = "{:+,.0f}"
            delta_pos_cols.append(col)
        elif col in ("LF+AM Long Positions", "LF+AM Short Positions", "Total OI"):
            format_dict[col] = "{:,.0f}"

    colored_cols = delta_pct_cols + delta_pos_cols

    styled = df.style.format(format_dict, na_rep="—")

    # Apply conditional coloring to all delta columns
    if colored_cols:
        if hasattr(styled, "map"):
            styled = styled.map(style_delta, subset=colored_cols)
        else:
            styled = styled.applymap(style_delta, subset=colored_cols)

    styled = styled.set_properties(**{
        "text-align": "center",
        "font-size": "0.82rem",
    })

    return styled



def format_historical_dataframe(df: pd.DataFrame):
    """Apply formatting to the historical DataFrame."""
    format_dict = {}
    delta_cols = []
    
    for col in df.columns:
        if "Net Pos" in col:
            format_dict[col] = "{:,.0f}"
        elif "Net %" in col:
            format_dict[col] = "{:.2f}%"
        elif "Δ" in col:
            format_dict[col] = "{:+.2f}%"
            delta_cols.append(col)
            
    styled = df.style.format(format_dict, na_rep="—")
    
    # Apply conditional coloring to delta columns
    if delta_cols:
        if hasattr(styled, "map"):
            styled = styled.map(style_delta, subset=delta_cols)
        else:
            styled = styled.applymap(style_delta, subset=delta_cols)
            
    styled = styled.set_properties(**{
        "text-align": "center",
        "font-size": "0.85rem",
    })
    return styled


def format_lf_detail_dataframe(df: pd.DataFrame):
    """Apply formatting to the Leveraged Funds detail DataFrame."""
    format_dict = {}
    colored_cols = []
    
    for col in df.columns:
        if "($B)" in col:
            # Dollar columns — show with sign but NO color styling, no $ prefix in cell
            format_dict[col] = "{:+,.2f}"
        elif "Δ" in col or "delta" in col.lower():
            colored_cols.append(col)
            if "%" in col:
                format_dict[col] = "{:+.2f}%"
            else:
                format_dict[col] = "{:+,.0f}"
        elif "Net" in col:
            colored_cols.append(col)
            if "Percent" in col or "%" in col:
                format_dict[col] = "{:.2f}%"
            else:
                format_dict[col] = "{:,.0f}"
        elif "%" in col:
            format_dict[col] = "{:.2f}%"
        else:
            format_dict[col] = "{:,.0f}"

    styled = df.style.format(format_dict, na_rep="\u2014")

    # Apply conditional red/green coloring to Net Positions, Net Percent, Net Percent LF, all Delta columns, and $B columns
    if colored_cols:
        if hasattr(styled, "map"):
            styled = styled.map(style_delta, subset=colored_cols)
        else:
            styled = styled.applymap(style_delta, subset=colored_cols)

    styled = styled.set_properties(**{
        "text-align": "center",
        "font-size": "0.82rem",
    })
    return styled




def clean_html_string(html: str) -> str:
    """Strip all leading whitespace from each line of the HTML string to avoid markdown code block parsing."""
    return "\n".join(line.strip() for line in html.strip().split("\n"))


def render_copy_button(df: pd.DataFrame, key: str):
    """Render a Copy Table to Clipboard button for a DataFrame."""
    if df.empty:
        return
    tsv_data = df.to_csv(sep="\t", index=True).replace("`", "\\`").replace("$", "\\$")
    btn_id = f"copy-btn-{key}"
    js_func_name = f"copyTable_{key.replace('-', '_')}"
    copy_html = f"""
    <div style="text-align: right; margin-bottom: 6px;">
        <button id="{btn_id}" onclick="{js_func_name}()" style="
            background-color: #6366f1;
            color: white;
            border: none;
            padding: 0.4rem 0.8rem;
            font-size: 0.85rem;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s ease;
            width: 100%;
        ">
            Copy Table to Clipboard
        </button>
    </div>
    <script>
    function {js_func_name}() {{
        const text = `{tsv_data}`;
        navigator.clipboard.writeText(text).then(() => {{
            const btn = document.getElementById('{btn_id}');
            btn.innerText = 'Copied!';
            btn.style.backgroundColor = '#16a34a';
            setTimeout(() => {{
                btn.innerText = 'Copy Table to Clipboard';
                btn.style.backgroundColor = '#6366f1';
            }}, 2000);
        }}).catch(err => {{
            console.error('Failed to copy: ', err);
        }});
    }}
    </script>
    """
    st.components.v1.html(copy_html, height=42)


def clean_currency_name(name: str) -> str:
    """Clean currency names for pairs display (e.g. 'USD (DXY)' -> 'USD')."""
    return name.split(" ")[0]


def calculate_strength_pairs(df: pd.DataFrame, cat_short: str):
    """
    Calculate currency pairs based on delta values for a given category.
    Returns a list of tuples: (strong_curr, weak_curr, strong_val, weak_val)
    sorted from strongest to weakest difference.
    """
    delta_col = f"{cat_short} Δ"
    if delta_col not in df.columns:
        return []
    
    # Get currencies and their delta values
    series = df[delta_col].dropna()
    if len(series) < 2:
        return []
    
    # Sort descending
    sorted_series = series.sort_values(ascending=False)
    currencies = sorted_series.index.tolist()
    values = sorted_series.values.tolist()
    
    pairs = []
    n = len(currencies)
    # We pair index i with index n - 1 - i
    # S1 vs W1, S2 vs W2, S3 vs W3, S4 vs W4
    for i in range(n // 2):
        strong_curr = currencies[i]
        weak_curr = currencies[n - 1 - i]
        strong_val = values[i]
        weak_val = values[n - 1 - i]
        pairs.append((strong_curr, weak_curr, strong_val, weak_val))
        
    return pairs


def render_lf_strength_grid(df_lf_detail: pd.DataFrame):
    """Render 28-currency pair LF Strength Index grid with dynamic gradient styling."""
    if df_lf_detail.empty:
        return
        
    lf_pairs = calculate_lf_strength_index(df_lf_detail)
    if not lf_pairs:
        return

    grid_html = """
    <div style="
        background: #ffffff;
        padding: 1.25rem 1.5rem;
        border-radius: 12px;
        border: 1px solid rgba(99, 102, 241, 0.25);
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
        margin-top: 0.5rem;
        margin-bottom: 1rem;
        overflow-x: auto;
    ">
        <table style="
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-family: 'Inter', sans-serif;
            text-align: center;
        ">
    """
    
    chunk_size = 7
    for i in range(0, len(lf_pairs), chunk_size):
        chunk = lf_pairs[i:i + chunk_size]
        
        # Pair Names Row
        grid_html += '<tr>'
        for pair_symbol, _ in chunk:
            grid_html += f"""
            <td style="
                padding: 8px 6px 2px 6px;
                font-weight: 700;
                font-size: 0.95rem;
                color: #1e1b4b;
                border-bottom: none;
            ">{pair_symbol}</td>
            """
        grid_html += '</tr>'
        
        # Percentage Values Row with dynamic gradient & black font color
        grid_html += '<tr>'
        for _, val in chunk:
            abs_ratio = min(abs(val) / 50.0, 1.0)
            alpha = 0.15 + (abs_ratio * 0.45)
            if val >= 0:
                bg_color = f"rgba(34, 197, 94, {alpha:.2f})"
            else:
                bg_color = f"rgba(239, 68, 68, {alpha:.2f})"

            grid_html += f"""
            <td style="
                padding: 2px 6px 10px 6px;
                font-weight: 600;
                font-size: 0.88rem;
                color: #000000;
            ">
                <span style="
                    background: {bg_color};
                    color: #000000;
                    padding: 4px 10px;
                    border-radius: 6px;
                    display: inline-block;
                    min-width: 55px;
                ">
                    {val:+.2f}%
                </span>
            </td>
            """
        grid_html += '</tr>'
        
    grid_html += """
        </table>
    </div>
    """
    st.markdown(clean_html_string(grid_html), unsafe_allow_html=True)



def get_score_gradient_style(val: float, is_pair: bool = False):
    """
    Generate dynamic green/red gradient background styling with BLACK font color based on score magnitude.
    - Positive scores: light green to dark green background
    - Negative scores: light red to dark red (or low currency scores 0 to 50) background
    """
    if pd.isna(val) or val is None:
        return "color: #000000;"

    if is_pair:
        abs_ratio = min(abs(val) / 60.0, 1.0)
        alpha = 0.15 + (abs_ratio * 0.45)
        
        if val >= 0:
            bg_color = f"rgba(34, 197, 94, {alpha:.2f})"
        else:
            bg_color = f"rgba(239, 68, 68, {alpha:.2f})"
    else:
        diff = val - 50.0
        abs_ratio = min(abs(diff) / 50.0, 1.0)
        alpha = 0.15 + (abs_ratio * 0.45)

        if val >= 50:
            bg_color = f"rgba(34, 197, 94, {alpha:.2f})"
        else:
            bg_color = f"rgba(239, 68, 68, {alpha:.2f})"

    return f"color: #000000; background-color: {bg_color}; font-weight: 600;"


def render_currency_composite_scores(df_lf_detail: pd.DataFrame, weights: dict, key_suffix: str = "curr"):
    """Render Currency Level Component & Composite Scores table."""
    if df_lf_detail.empty:
        return

    curr_df, composite_pairs = calculate_lf_composite_index(df_lf_detail, weights=weights)
    if curr_df.empty:
        return

    st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
    header_col, copy_col = st.columns([7, 3])
    with header_col:
        st.markdown("### Currency Level Component & Composite Scores")
    with copy_col:
        render_copy_button(curr_df.set_index("Currency"), f"comp-scores-{key_suffix}")
    
    # Format Currency Table - apply color coding ONLY to "Composite Score"
    def style_currency_table(df):
        style_df = pd.DataFrame('', index=df.index, columns=df.columns)
        if "Composite Score" in df.columns:
            style_df["Composite Score"] = df["Composite Score"].apply(lambda v: get_score_gradient_style(v, is_pair=False))
        return style_df

    curr_styled = curr_df.style.format({
        "LF Strength": "{:.2f}",
        "LF Delta": "{:.2f}",
        "LF OI Momentum": "{:.2f}",
        "Composite Score": "{:.2f}",
    }).apply(style_currency_table, axis=None).set_properties(**{
        "text-align": "center",
        "font-size": "0.85rem",
    })
    st.dataframe(curr_styled, use_container_width=True)


def render_lf_strength_grid(df_lf_detail: pd.DataFrame, key_suffix: str = "curr"):
    """Render 28-currency pair LF Strength Index grid with dynamic gradient styling."""
    if df_lf_detail.empty:
        return
        
    lf_pairs = calculate_lf_strength_index(df_lf_detail)
    if not lf_pairs:
        return

    st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
    header_col, copy_col = st.columns([7, 3])
    with header_col:
        st.markdown("### Currency Pairs — LF Strength Index")
    with copy_col:
        df_pairs = pd.DataFrame(lf_pairs, columns=["Pair", "LF Strength Index"]).set_index("Pair")
        render_copy_button(df_pairs, f"lf-strength-{key_suffix}")

    grid_html = """
    <div style="
        background: #ffffff;
        padding: 1.25rem 1.5rem;
        border-radius: 12px;
        border: 1px solid rgba(99, 102, 241, 0.25);
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
        margin-top: 0.5rem;
        margin-bottom: 1rem;
        overflow-x: auto;
    ">
        <table style="
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-family: 'Inter', sans-serif;
            text-align: center;
        ">
    """
    
    chunk_size = 7
    for i in range(0, len(lf_pairs), chunk_size):
        chunk = lf_pairs[i:i + chunk_size]
        
        # Pair Names Row
        grid_html += '<tr>'
        for pair_symbol, _ in chunk:
            grid_html += f"""
            <td style="
                padding: 8px 6px 2px 6px;
                font-weight: 700;
                font-size: 0.95rem;
                color: #1e1b4b;
                border-bottom: none;
            ">{pair_symbol}</td>
            """
        grid_html += '</tr>'
        
        # Percentage Values Row with dynamic gradient & black font color
        grid_html += '<tr>'
        for _, val in chunk:
            abs_ratio = min(abs(val) / 50.0, 1.0)
            alpha = 0.15 + (abs_ratio * 0.45)
            if val >= 0:
                bg_color = f"rgba(34, 197, 94, {alpha:.2f})"
            else:
                bg_color = f"rgba(239, 68, 68, {alpha:.2f})"

            grid_html += f"""
            <td style="
                padding: 2px 6px 10px 6px;
                font-weight: 600;
                font-size: 0.88rem;
                color: #000000;
            ">
                <span style="
                    background: {bg_color};
                    color: #000000;
                    padding: 4px 10px;
                    border-radius: 6px;
                    display: inline-block;
                    min-width: 55px;
                ">
                    {val:+.2f}%
                </span>
            </td>
            """
        grid_html += '</tr>'
        
    grid_html += """
        </table>
    </div>
    """
    st.markdown(clean_html_string(grid_html), unsafe_allow_html=True)


def render_lf_composite_strength_grid(df_lf_detail: pd.DataFrame, weights: dict, key_suffix: str = "curr"):
    """Render Currency Pairs — LF Composite Strength Index table."""
    if df_lf_detail.empty:
        return

    curr_df, composite_pairs = calculate_lf_composite_index(df_lf_detail, weights=weights)
    if not composite_pairs:
        return

    st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
    header_col, copy_col = st.columns([7, 3])
    with header_col:
        st.markdown("### Currency Pairs — LF Composite Strength Index")
    with copy_col:
        df_comp_pairs = pd.DataFrame(composite_pairs, columns=["Pair", "Composite Strength Score"]).set_index("Pair")
        render_copy_button(df_comp_pairs, f"lf-comp-{key_suffix}")

    grid_html = """
    <div style="
        background: #ffffff;
        padding: 1.25rem 1.5rem;
        border-radius: 12px;
        border: 1px solid rgba(99, 102, 241, 0.25);
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
        margin-top: 0.5rem;
        margin-bottom: 1rem;
        overflow-x: auto;
    ">
        <table style="
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-family: 'Inter', sans-serif;
            text-align: center;
        ">
    """

    chunk_size = 7
    for i in range(0, len(composite_pairs), chunk_size):
        chunk = composite_pairs[i:i + chunk_size]

        # Pair Names Row
        grid_html += '<tr>'
        for pair_symbol, _ in chunk:
            grid_html += f"""
            <td style="
                padding: 8px 6px 2px 6px;
                font-weight: 700;
                font-size: 0.95rem;
                color: #1e1b4b;
                border-bottom: none;
            ">{pair_symbol}</td>
            """
        grid_html += '</tr>'

        # Score Values Row with dynamic gradient and BLACK font color
        grid_html += '<tr>'
        for _, val in chunk:
            abs_ratio = min(abs(val) / 60.0, 1.0)
            alpha = 0.15 + (abs_ratio * 0.45)
            if val >= 0:
                bg_color = f"rgba(34, 197, 94, {alpha:.2f})"
            else:
                bg_color = f"rgba(239, 68, 68, {alpha:.2f})"

            grid_html += f"""
            <td style="
                padding: 2px 6px 10px 6px;
                font-weight: 600;
                font-size: 0.88rem;
                color: #000000;
            ">
                <span style="
                    background: {bg_color};
                    color: #000000;
                    padding: 4px 10px;
                    border-radius: 6px;
                    display: inline-block;
                    min-width: 55px;
                ">
                    {val:+.2f}
                </span>
            </td>
            """
        grid_html += '</tr>'

    grid_html += """
        </table>
    </div>
    """
    st.markdown(clean_html_string(grid_html), unsafe_allow_html=True)







# ──────────────────────────────────────────────────────────────────────
# Main App
# ──────────────────────────────────────────────────────────────────────
def main():
    # Load LF Strength Index weights dynamically from json file
    try:
        with open("weights.json", "r") as f:
            lf_weights = json.load(f)
    except Exception:
        lf_weights = {
            "strength": 0.60,
            "delta": 0.25,
            "oi_momentum": 0.15
        }

    # ── Header ──
    st.markdown("""
    <div class="main-header">
        <h1>COT Analyzer Dashboard</h1>
        <div class="subtitle">
            Commitments of Traders — Financial Futures (Futures Only)
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ── Controls & Status Row ──
    # Get all release dates up to today (increase count for deeper history)
    all_dates = get_recent_release_dates(count=200)
    recent_dates = [d for d in all_dates if d <= date.today()]
    
    col1, col2, col3, _ = st.columns([2, 3, 3, 4])
    with col1:
        if st.button("Refresh Data", use_container_width=True, type="primary"):
            # Do not clear the entire cache; rely on disk cache to avoid re‑fetching existing weeks
            st.rerun()
            
    with col2:
        if len(recent_dates) > 0:
            st.markdown(
                f'<div class="date-badge">Current: {recent_dates[0].strftime("%b %d, %Y")}</div>',
                unsafe_allow_html=True,
            )
            
    with col3:
        if len(recent_dates) > 1:
            st.markdown(
                f'<div class="date-badge">Previous: {recent_dates[1].strftime("%b %d, %Y")}</div>',
                unsafe_allow_html=True,
            )
            
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Load Data ──
    # All weeks — including the current/latest release — are fetched through
    # the unified disk-cache-first loader.  The most-recent release date gets
    # is_latest=True so it falls back to the live CFTC URL if the archive
    # URL for that date is not yet available.
    reports_data = []
    comm_reports_data = []

    with st.spinner("Loading COT report history..."):
        total_dates = len(recent_dates)

        if total_dates > 0:
            progress_bar = st.progress(0.0)
            progress_text = st.empty()

            for idx, rel_date in enumerate(recent_dates):
                progress_percent = (idx + 1) / total_dates
                progress_bar.progress(progress_percent)
                date_str = rel_date.isoformat()
                is_latest = (idx == 0)  # most-recent release date

                progress_text.text(
                    f"Loading {'current' if is_latest else 'archive'} report for "
                    f"{rel_date.strftime('%b %d, %Y')} ({idx+1}/{total_dates})..."
                )

                week = load_week_data(date_str, is_latest=is_latest)
                if week:
                    reports_data.append(week)
                elif is_latest:
                    progress_bar.empty()
                    progress_text.empty()
                    st.error("Failed to fetch current week data.")
                    return

                comm_week = load_commodity_week_data(date_str, is_latest=is_latest)
                if comm_week:
                    comm_reports_data.append(comm_week)

            progress_bar.empty()
            progress_text.empty()
        else:
            st.error("No release dates found.")
            return

    # Deduplicate reports by report_date to prevent non-unique index errors
    seen_dates = set()
    deduped_reports = []
    for r in reports_data:
        if r and "report_date" in r and r["report_date"]:
            d = r["report_date"]
            if d not in seen_dates:
                seen_dates.add(d)
                deduped_reports.append(r)
    reports_data = deduped_reports
    
    seen_comm_dates = set()
    deduped_comm_reports = []
    for r in comm_reports_data:
        if r and "report_date" in r and r["report_date"]:
            d = r["report_date"]
            if d not in seen_comm_dates:
                seen_comm_dates.add(d)
                deduped_comm_reports.append(r)
    comm_reports_data = deduped_comm_reports

    if not reports_data:
        st.error("No data available.")
        return

    current_data = reports_data[0]
    previous_data = reports_data[1] if len(reports_data) > 1 else None

    # ── Load & Render Commodity Table (Before Current Week Overview) ──
    comm_current = comm_reports_data[0] if comm_reports_data else None
    comm_previous = comm_reports_data[1] if len(comm_reports_data) > 1 else None

    df_commodity_history = compute_commodity_historical_table(comm_reports_data)

    if comm_current:
        df_commodity = compute_commodity_table(comm_current, comm_previous)
        if not df_commodity.empty:
            comm_header_col, comm_copy_col = st.columns([7, 3])
            with comm_header_col:
                st.markdown("### Commodity COT (Disaggregated Managed Money)")
            with comm_copy_col:
                render_copy_button(df_commodity, "commodity-overview")

            styled_commodity = format_commodity_dataframe(df_commodity)
            st.dataframe(styled_commodity, use_container_width=True)


    # ── Consolidated Table (Current Week) ──
    df_consolidated = compute_consolidated_table(current_data, previous_data)
    
    header_col, copy_col = st.columns([7, 3])
    with header_col:
        st.markdown("### Current Week Overview")
    with copy_col:
        if not df_consolidated.empty:
            tsv_data = df_consolidated.to_csv(sep="\t", index=True).replace("`", "\\`").replace("$", "\\$")
            copy_html = f"""
            <div style="text-align: right;">
                <button id="copy-btn" onclick="copyTableToClipboard()" style="
                    background-color: #6366f1;
                    color: white;
                    border: none;
                    padding: 0.4rem 0.8rem;
                    font-size: 0.85rem;
                    font-weight: 600;
                    border-radius: 6px;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    width: 100%;
                ">
                    Copy Table to Clipboard
                </button>
            </div>
            <script>
            function copyTableToClipboard() {{
                const text = `{tsv_data}`;
                navigator.clipboard.writeText(text).then(() => {{
                    const btn = document.getElementById('copy-btn');
                    btn.innerText = 'Copied!';
                    btn.style.backgroundColor = '#16a34a';
                    setTimeout(() => {{
                        btn.innerText = 'Copy Table to Clipboard';
                        btn.style.backgroundColor = '#6366f1';
                    }}, 2000);
                }}).catch(err => {{
                    console.error('Failed to copy: ', err);
                }});
            }}
            </script>
            """
            st.components.v1.html(copy_html, height=45)
            
    if not df_consolidated.empty:
        styled_consolidated = format_consolidated_dataframe(df_consolidated)
        st.dataframe(styled_consolidated, use_container_width=True)
    else:
        st.warning("No data found for current week.")

    # Pre-compute historical tables for the visualizations and history section
    df_history = compute_historical_table(reports_data)
    df_lf_history = compute_lf_detail_historical_table(reports_data)

    # ── Leveraged Funds Detail Table (Current Week) ──
    df_lf_detail = compute_lf_detail_table(current_data, previous_data)
    if not df_lf_detail.empty:
        lf_breakdown_cols = [
            "Net Positions", "Net Percent", "Net Percent LF", "Net % LF Δ",
            "LF longs Δ", "LF short Δ"
        ]
        df_lf_breakdown = df_lf_detail[[c for c in lf_breakdown_cols if c in df_lf_detail.columns]]
        
        st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
        lf_header_col, lf_copy_col = st.columns([7, 3])
        with lf_header_col:
            st.markdown("### Leveraged Funds Breakdown")
        with lf_copy_col:
            tsv_lf_data = df_lf_breakdown.to_csv(sep="\t", index=True).replace("`", "\\`").replace("$", "\\$")
            copy_lf_html = f"""
            <div style="text-align: right;">
                <button id="copy-lf-btn" onclick="copyLfTableToClipboard()" style="
                    background-color: #6366f1;
                    color: white;
                    border: none;
                    padding: 0.4rem 0.8rem;
                    font-size: 0.85rem;
                    font-weight: 600;
                    border-radius: 6px;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    width: 100%;
                ">
                    Copy Table to Clipboard
                </button>
            </div>
            <script>
            function copyLfTableToClipboard() {{
                const text = `{tsv_lf_data}`;
                navigator.clipboard.writeText(text).then(() => {{
                    const btn = document.getElementById('copy-lf-btn');
                    btn.innerText = 'Copied!';
                    btn.style.backgroundColor = '#16a34a';
                    setTimeout(() => {{
                        btn.innerText = 'Copy Table to Clipboard';
                        btn.style.backgroundColor = '#6366f1';
                    }}, 2000);
                }}).catch(err => {{
                    console.error('Failed to copy: ', err);
                }});
            }}
            </script>
            """
            st.components.v1.html(copy_lf_html, height=45)

        styled_lf_detail = format_lf_detail_dataframe(df_lf_breakdown)
        st.dataframe(styled_lf_detail, use_container_width=True)

        # ── COT Detailed Breakdown (Current Week) ──
        detailed_cols = [
            "Δ Total Open Interest", "Δ LF Open Interest",
            "Δ LF Longs ($B)", "Δ LF Shorts ($B)", "Δ AM Longs ($B)", "Δ AM Shorts ($B)",
            "AM long Δ", "AM short Δ"
        ]
        df_detailed = df_lf_detail[[c for c in detailed_cols if c in df_lf_detail.columns]]
        
        st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
        det_header_col, det_copy_col = st.columns([7, 3])
        with det_header_col:
            st.markdown("### COT Detailed Breakdown")
        with det_copy_col:
            tsv_det_data = df_detailed.to_csv(sep="\t", index=True).replace("`", "\\`").replace("$", "\\$")
            copy_det_html = f"""
            <div style="text-align: right;">
                <button id="copy-det-btn" onclick="copyDetTableToClipboard()" style="
                    background-color: #6366f1;
                    color: white;
                    border: none;
                    padding: 0.4rem 0.8rem;
                    font-size: 0.85rem;
                    font-weight: 600;
                    border-radius: 6px;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    width: 100%;
                ">
                    Copy Table to Clipboard
                </button>
            </div>
            <script>
            function copyDetTableToClipboard() {{
                const text = `{tsv_det_data}`;
                navigator.clipboard.writeText(text).then(() => {{
                    const btn = document.getElementById('copy-det-btn');
                    btn.innerText = 'Copied!';
                    btn.style.backgroundColor = '#16a34a';
                    setTimeout(() => {{
                        btn.innerText = 'Copy Table to Clipboard';
                        btn.style.backgroundColor = '#6366f1';
                    }}, 2000);
                }}).catch(err => {{
                    console.error('Failed to copy: ', err);
                }});
            }}
            </script>
            """
            st.components.v1.html(copy_det_html, height=45)

        styled_detailed = format_lf_detail_dataframe(df_detailed)
        st.dataframe(styled_detailed, use_container_width=True)


        # ── Historical + Current Visualization ──
        if not df_history.empty and not df_lf_history.empty:
            st.markdown("<hr style='border: 1px solid rgba(255,255,255,0.05); margin: 2rem 0;'>", unsafe_allow_html=True)
            st.markdown("### Position Visualization")
            
            # Get unique currencies for dropdowns
            available_currencies = df_history.index.get_level_values("Currency").unique().tolist()
            
            # We need the report dates
            available_dates = df_history.index.get_level_values("Report Date").unique().tolist()
            
            num_weeks = st.selectbox("Historical Weeks to View", options=[4, 7, 12, 24, 52], index=1)
            chart_dates = available_dates[:num_weeks]
            
            col_left, col_right = st.columns(2)
            
            with col_left:
                curr_left = st.selectbox("Select Currency 1 (Left)", options=available_currencies, index=0, key="curr_left")
                
                if curr_left:
                    st.markdown(f"**{curr_left} - LF & AM Positioning (Last {len(chart_dates)} Weeks)**")
                    # Filter data for curr_left and chart_dates
                    df_hist_left = df_history.loc[df_history.index.get_level_values("Currency") == curr_left]
                    df_hist_left = df_hist_left[df_hist_left.index.get_level_values("Report Date").isin(chart_dates)].reset_index()
                    
                    df_lf_hist_left = df_lf_history.loc[df_lf_history.index.get_level_values("Currency") == curr_left]
                    df_lf_hist_left = df_lf_hist_left[df_lf_hist_left.index.get_level_values("Report Date").isin(chart_dates)].reset_index()
                    
                    # Reverse to plot chronological order (oldest to newest)
                    df_hist_left = df_hist_left.iloc[::-1]
                    df_lf_hist_left = df_lf_hist_left.iloc[::-1]
                    
                    # LF Chart
                    lf_melt_left = df_lf_hist_left.melt(
                        id_vars=["Report Date"],
                        value_vars=["Net Percent LF", "Net % LF Δ"],
                        var_name="Metric",
                        value_name="Value"
                    )
                    fig_lf_left = px.bar(lf_melt_left, x="Report Date", y="Value", color="Metric", barmode="group",
                                         color_discrete_sequence=["#1a80bb", "#ea801c"], template="plotly_dark",
                                         title="Leveraged Funds (LF)")
                    fig_lf_left.update_layout(margin=dict(l=20, r=20, t=30, b=20), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig_lf_left, use_container_width=True)
                    
                    # AM Chart
                    am_melt_left = df_hist_left.melt(
                        id_vars=["Report Date"],
                        value_vars=["AM Net %", "AM Δ"],
                        var_name="Metric",
                        value_name="Value"
                    )
                    am_melt_left["Metric"] = am_melt_left["Metric"].replace({"AM Net %": "Net Percent AM", "AM Δ": "Net % AM Δ"})
                    fig_am_left = px.bar(am_melt_left, x="Report Date", y="Value", color="Metric", barmode="group",
                                         color_discrete_sequence=["#298c8c", "#f1a226"], template="plotly_dark",
                                         title="Asset Manager (AM)")
                    fig_am_left.update_layout(margin=dict(l=20, r=20, t=30, b=20), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig_am_left, use_container_width=True)
                    
            with col_right:
                curr_right = st.selectbox("Select Currency 2 (Right)", options=available_currencies, index=min(1, len(available_currencies)-1), key="curr_right")
                
                if curr_right:
                    st.markdown(f"**{curr_right} - LF & AM Positioning (Last {len(chart_dates)} Weeks)**")
                    # Filter data for curr_right and chart_dates
                    df_hist_right = df_history.loc[df_history.index.get_level_values("Currency") == curr_right]
                    df_hist_right = df_hist_right[df_hist_right.index.get_level_values("Report Date").isin(chart_dates)].reset_index()
                    
                    df_lf_hist_right = df_lf_history.loc[df_lf_history.index.get_level_values("Currency") == curr_right]
                    df_lf_hist_right = df_lf_hist_right[df_lf_hist_right.index.get_level_values("Report Date").isin(chart_dates)].reset_index()
                    
                    # Reverse to plot chronological order (oldest to newest)
                    df_hist_right = df_hist_right.iloc[::-1]
                    df_lf_hist_right = df_lf_hist_right.iloc[::-1]
                    
                    # LF Chart
                    lf_melt_right = df_lf_hist_right.melt(
                        id_vars=["Report Date"],
                        value_vars=["Net Percent LF", "Net % LF Δ"],
                        var_name="Metric",
                        value_name="Value"
                    )
                    fig_lf_right = px.bar(lf_melt_right, x="Report Date", y="Value", color="Metric", barmode="group",
                                          color_discrete_sequence=["#1a80bb", "#ea801c"], template="plotly_dark",
                                          title="Leveraged Funds (LF)")
                    fig_lf_right.update_layout(margin=dict(l=20, r=20, t=30, b=20), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig_lf_right, use_container_width=True)
                    
                    # AM Chart
                    am_melt_right = df_hist_right.melt(
                        id_vars=["Report Date"],
                        value_vars=["AM Net %", "AM Δ"],
                        var_name="Metric",
                        value_name="Value"
                    )
                    am_melt_right["Metric"] = am_melt_right["Metric"].replace({"AM Net %": "Net Percent AM", "AM Δ": "Net % AM Δ"})
                    fig_am_right = px.bar(am_melt_right, x="Report Date", y="Value", color="Metric", barmode="group",
                                          color_discrete_sequence=["#298c8c", "#f1a226"], template="plotly_dark",
                                          title="Asset Manager (AM)")
                    fig_am_right.update_layout(margin=dict(l=20, r=20, t=30, b=20), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig_am_right, use_container_width=True)

        render_lf_strength_grid(df_lf_detail, key_suffix="curr")
        render_lf_composite_strength_grid(df_lf_detail, weights=lf_weights, key_suffix="curr")
        render_currency_composite_scores(df_lf_detail, weights=lf_weights, key_suffix="curr")

        # ── Commodity Position Visualization ──
        if not df_commodity_history.empty:
            st.markdown("<hr style='border: 1px solid rgba(255,255,255,0.05); margin: 2rem 0;'>", unsafe_allow_html=True)
            st.markdown("### Commodity Position Visualization")
            
            available_commodities = df_commodity_history.index.get_level_values("Commodity").unique().tolist()
            available_comm_dates = df_commodity_history.index.get_level_values("Report Date").unique().tolist()
            
            c_weeks = st.selectbox("Historical Weeks to View", options=[4, 7, 12, 24, 52], index=1, key="comm_weeks")
            comm_chart_dates = available_comm_dates[:c_weeks]
            
            selected_commodity = st.selectbox("Select Commodity", options=available_commodities, index=0, key="comm_select")
            
            if selected_commodity:
                # Filter data
                df_comm_hist_sel = df_commodity_history.loc[df_commodity_history.index.get_level_values("Commodity") == selected_commodity]
                df_comm_hist_sel = df_comm_hist_sel[df_comm_hist_sel.index.get_level_values("Report Date").isin(comm_chart_dates)].reset_index()
                df_comm_hist_sel = df_comm_hist_sel.iloc[::-1] # Oldest to newest
                
                ccol1, ccol2 = st.columns(2)
                
                with ccol1:
                    st.markdown(f"**{selected_commodity} - Net vs Δ Net**")
                    melt_net = df_comm_hist_sel.melt(
                        id_vars=["Report Date"],
                        value_vars=["Net", "Δ Net"],
                        var_name="Metric",
                        value_name="Contracts"
                    )
                    fig_comm_net = px.bar(melt_net, x="Report Date", y="Contracts", color="Metric", barmode="group",
                                         color_discrete_sequence=["#1a80bb", "#ea801c"], template="plotly_dark",
                                         title="Net Positions")
                    fig_comm_net.update_layout(margin=dict(l=20, r=20, t=30, b=20), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig_comm_net, use_container_width=True)
                    
                with ccol2:
                    st.markdown(f"**{selected_commodity} - Long/Short vs Δ**")
                    melt_ls = df_comm_hist_sel.melt(
                        id_vars=["Report Date"],
                        value_vars=["Long", "Δ Long", "Short", "Δ Short"],
                        var_name="Metric",
                        value_name="Contracts"
                    )
                    fig_comm_ls = px.bar(melt_ls, x="Report Date", y="Contracts", color="Metric", barmode="group",
                                        color_discrete_sequence=["#298c8c", "#4ade80", "#f87171", "#f1a226"], template="plotly_dark",
                                        title="Long & Short Positions")
                    fig_comm_ls.update_layout(margin=dict(l=20, r=20, t=30, b=20), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig_comm_ls, use_container_width=True)

        st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)

    # ── Historical Data (Last X Reports) ──
    st.markdown(f"### Historical Data (Last {len(reports_data)} Reports)")
    
    if not df_history.empty:
        # df_history has a MultiIndex: ["Currency", "Report Date"]
        # We extract unique dates (they preserve order from reports_data)
        dates = df_history.index.get_level_values("Report Date").unique()
        
        for idx, d in enumerate(dates):
            date_key = str(d).replace("-", "").replace(" ", "_")
            with st.expander(f"Report Date: {d}", expanded=(idx == 0)):
                # Extract cross-section for this date
                df_date = df_history.xs(d, level="Report Date")
                
                hist_header_col, hist_copy_col = st.columns([7, 3])
                with hist_header_col:
                    st.markdown("#### Overview")
                with hist_copy_col:
                    render_copy_button(df_date, f"hist-overview-{date_key}")

                styled_history = format_historical_dataframe(df_date)
                st.dataframe(styled_history, use_container_width=True)

                if not df_lf_history.empty and d in df_lf_history.index.get_level_values("Report Date"):
                    df_date_lf = df_lf_history.xs(d, level="Report Date")
                    
                    lf_breakdown_cols_hist = [
                        "Net Positions", "Net Percent", "Net Percent LF", "Net % LF Δ",
                        "LF longs Δ", "LF short Δ"
                    ]
                    df_lf_breakdown_hist = df_date_lf[[c for c in lf_breakdown_cols_hist if c in df_date_lf.columns]]
                    
                    lf_hist_header_col, lf_hist_copy_col = st.columns([7, 3])
                    with lf_hist_header_col:
                        st.markdown("#### Leveraged Funds Breakdown")
                    with lf_hist_copy_col:
                        render_copy_button(df_lf_breakdown_hist, f"hist-lf-{date_key}")

                    styled_date_lf = format_lf_detail_dataframe(df_lf_breakdown_hist)
                    st.dataframe(styled_date_lf, use_container_width=True)
                    
                    # ── Historical COT Detailed Breakdown ──
                    detailed_cols_hist = [
                        "Δ Total Open Interest", "Δ LF Open Interest",
                        "Δ LF Longs ($B)", "Δ LF Shorts ($B)", "Δ AM Longs ($B)", "Δ AM Shorts ($B)",
                        "AM long Δ", "AM short Δ"
                    ]
                    df_detailed_hist = df_date_lf[[c for c in detailed_cols_hist if c in df_date_lf.columns]]
                    
                    det_hist_header_col, det_hist_copy_col = st.columns([7, 3])
                    with det_hist_header_col:
                        st.markdown("#### COT Detailed Breakdown")
                    with det_hist_copy_col:
                        render_copy_button(df_detailed_hist, f"hist-det-{date_key}")
                        
                    styled_detailed_hist = format_lf_detail_dataframe(df_detailed_hist)
                    st.dataframe(styled_detailed_hist, use_container_width=True)
                    
                    render_currency_composite_scores(df_date_lf, weights=lf_weights, key_suffix=f"hist-{date_key}")
                    render_lf_strength_grid(df_date_lf, key_suffix=f"hist-{date_key}")
                    render_lf_composite_strength_grid(df_date_lf, weights=lf_weights, key_suffix=f"hist-{date_key}")
                
                # ── Historical Commodity Data ──
                if not df_commodity_history.empty and d in df_commodity_history.index.get_level_values("Report Date"):
                    df_date_comm = df_commodity_history.xs(d, level="Report Date")
                    
                    comm_hist_header_col, comm_hist_copy_col = st.columns([7, 3])
                    with comm_hist_header_col:
                        st.markdown("#### Commodity COT (Disaggregated Managed Money)")
                    with comm_hist_copy_col:
                        render_copy_button(df_date_comm, f"hist-comm-{date_key}")
                        
                    styled_comm_hist = format_commodity_dataframe(df_date_comm)
                    st.dataframe(styled_comm_hist, use_container_width=True)



    # ── Footer ──
    st.markdown(
        '<div class="footer">'
        "Data from CFTC Commitments of Traders Report • "
        "Traders in Financial Futures — Futures Only • "
        f"Dashboard refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        "</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()

