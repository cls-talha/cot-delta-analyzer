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
    padding: 0.6rem 0.8rem !important;
    border-bottom: 2px solid rgba(99,102,241,0.3) !important;
}
.dataframe td {
    text-align: center !important;
    padding: 0.5rem 0.8rem !important;
    border-bottom: 1px solid rgba(255,255,255,0.04) !important;
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


def get_cached_report(date_str: str) -> Optional[dict]:
    """Retrieve report from disk cache."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                cache = json.load(f)
                return cache.get(date_str)
        except Exception as e:
            print(f"[Cache] Error reading cache file: {e}")
    return None


def save_cached_report(date_str: str, report_data: dict):
    """Save report to disk cache."""
    try:
        cache = {}
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f:
                cache = json.load(f)
        
        cache[date_str] = report_data
        
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"[Cache] Error writing cache file: {e}")


@st.cache_data(ttl=3600, show_spinner=False)
def load_current_data():
    """Fetch and parse current week data (cached 1 hour)."""
    raw = fetch_current_week()
    if raw is None:
        return None
    return parse_report(raw)


@st.cache_data(ttl=3600, show_spinner=False)
def load_archive_data(release_date_str: str):
    """Fetch and parse archive week data (uses persistent disk cache + memory cache)."""
    # 1. Try disk cache first
    cached = get_cached_report(release_date_str)
    if cached:
        return cached

    # 2. Fetch from web
    parts = release_date_str.split("-")
    d = date(int(parts[0]), int(parts[1]), int(parts[2]))
    raw = fetch_archive_week(d)
    if raw is None:
        return None
    
    parsed = parse_report(raw)
    if parsed:
        # Save to disk cache
        save_cached_report(release_date_str, parsed)
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


def format_consolidated_dataframe(df: pd.DataFrame):
    """Apply formatting to the consolidated DataFrame."""
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

    # Style the rest
    styled = styled.set_properties(**{
        "text-align": "center",
        "font-size": "0.85rem",
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
        if "Δ" in col:
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

    styled = df.style.format(format_dict, na_rep="—")

    # Apply conditional red/green coloring to Net Positions, Net Percent, Net Percent LF and all Delta columns
    if colored_cols:
        if hasattr(styled, "map"):
            styled = styled.map(style_delta, subset=colored_cols)
        else:
            styled = styled.applymap(style_delta, subset=colored_cols)

    styled = styled.set_properties(**{
        "text-align": "center",
        "font-size": "0.85rem",
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


def render_currency_composite_scores(df_lf_detail: pd.DataFrame, key_suffix: str = "curr"):
    """Render Currency Level Component & Composite Scores table."""
    if df_lf_detail.empty:
        return

    curr_df, composite_pairs = calculate_lf_composite_index(df_lf_detail)
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


def render_lf_composite_strength_grid(df_lf_detail: pd.DataFrame, key_suffix: str = "curr"):
    """Render Currency Pairs — LF Composite Strength Index table."""
    if df_lf_detail.empty:
        return

    curr_df, composite_pairs = calculate_lf_composite_index(df_lf_detail)
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
    recent_dates = get_recent_release_dates(count=100)
    
    col1, col2, col3, _ = st.columns([2, 3, 3, 4])
    with col1:
        if st.button("Refresh Data", use_container_width=True, type="primary"):
            st.cache_data.clear()
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
    reports_data = []
    
    with st.spinner("Loading COT report history..."):
        current = load_current_data()
        if current:
            reports_data.append(current)
        else:
            st.error("Failed to fetch current week data.")
            return
            
        # We display a progress bar when loading from the web
        archive_dates = recent_dates[1:]
        total_dates = len(archive_dates)
        
        if total_dates > 0:
            progress_bar = st.progress(0.0)
            progress_text = st.empty()
            
            for idx, archive_date in enumerate(archive_dates):
                progress_percent = (idx + 1) / total_dates
                progress_bar.progress(progress_percent)
                progress_text.text(f"Loading archive report for {archive_date.strftime('%b %d, %Y')} ({idx+1}/{total_dates})...")
                
                arch = load_archive_data(archive_date.isoformat())
                if arch:
                    reports_data.append(arch)
                    
            progress_bar.empty()
            progress_text.empty()

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

    if not reports_data:
        st.error("No data available.")
        return

    current_data = reports_data[0]
    previous_data = reports_data[1] if len(reports_data) > 1 else None

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

    # ── Leveraged Funds Detail Table (Current Week) ──
    df_lf_detail = compute_lf_detail_table(current_data, previous_data)
    if not df_lf_detail.empty:
        st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
        lf_header_col, lf_copy_col = st.columns([7, 3])
        with lf_header_col:
            st.markdown("### Leveraged Funds Breakdown")
        with lf_copy_col:
            tsv_lf_data = df_lf_detail.to_csv(sep="\t", index=True).replace("`", "\\`").replace("$", "\\$")
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

        styled_lf_detail = format_lf_detail_dataframe(df_lf_detail)
        st.dataframe(styled_lf_detail, use_container_width=True)

        render_currency_composite_scores(df_lf_detail, key_suffix="curr")
        render_lf_strength_grid(df_lf_detail, key_suffix="curr")
        render_lf_composite_strength_grid(df_lf_detail, key_suffix="curr")

    st.markdown("<hr style='border: 1px solid rgba(255,255,255,0.05); margin: 2rem 0;'>", unsafe_allow_html=True)

    # ── Plotly Graphs ──
    if not df_consolidated.empty and previous_data:
        st.markdown("### Weekly Delta Visualization (%)")
        
        # Prepare data for plotting
        plot_df = df_consolidated.reset_index()
        delta_cols = [col for col in plot_df.columns if "Δ" in col]
        
        if delta_cols:
            # Melt the dataframe so we have Currency, Category, Delta
            melted = plot_df.melt(
                id_vars=["Currency"],
                value_vars=delta_cols,
                var_name="Category",
                value_name="Delta (%)"
            )
            
            # Clean category names (e.g., "LF Δ" -> "Leveraged Funds")
            cat_map = {"LF Δ": "Leveraged Funds", "AM Δ": "Asset Manager", "DI Δ": "Dealers"}
            melted["Category"] = melted["Category"].map(cat_map)
            
            fig = px.bar(
                melted,
                x="Currency",
                y="Delta (%)",
                color="Category",
                barmode="group",
                color_discrete_sequence=["#f43f5e", "#3b82f6", "#10b981"], # Distinct colors
                template="plotly_dark"
            )
            
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=20, r=20, t=30, b=20),
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                xaxis_title="",
                yaxis_title="Change in Net % (bps)",
            )
            
            # Add horizontal zero line
            fig.add_hline(y=0, line_width=1, line_color="rgba(255,255,255,0.2)")
            
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("<hr style='border: 1px solid rgba(255,255,255,0.05); margin: 2rem 0;'>", unsafe_allow_html=True)

    # ── Historical Data (Last 3-4 Weeks) ──
    st.markdown(f"### Historical Data (Last {len(reports_data)} Reports)")
    df_history = compute_historical_table(reports_data)
    df_lf_history = compute_lf_detail_historical_table(reports_data)
    
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
                    
                    lf_hist_header_col, lf_hist_copy_col = st.columns([7, 3])
                    with lf_hist_header_col:
                        st.markdown("#### Leveraged Funds Breakdown")
                    with lf_hist_copy_col:
                        render_copy_button(df_date_lf, f"hist-lf-{date_key}")

                    styled_date_lf = format_lf_detail_dataframe(df_date_lf)
                    st.dataframe(styled_date_lf, use_container_width=True)
                    
                    render_currency_composite_scores(df_date_lf, key_suffix=f"hist-{date_key}")
                    render_lf_strength_grid(df_date_lf, key_suffix=f"hist-{date_key}")
                    render_lf_composite_strength_grid(df_date_lf, key_suffix=f"hist-{date_key}")



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

