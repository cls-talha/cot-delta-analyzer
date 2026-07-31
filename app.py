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

from cot_parser import parse_report
from cot_fetcher import fetch_current_week, fetch_archive_week, get_recent_release_dates
from cot_calculator import (
    compute_consolidated_table,
    compute_historical_table,
    compute_lf_detail_table,
    compute_lf_detail_historical_table,
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




    st.markdown("<hr style='border: 1px solid rgba(255,255,255,0.05); margin: 2rem 0;'>", unsafe_allow_html=True)

    # ── Weekly Strength Pairs (based on Delta) ──
    if not df_consolidated.empty:
        st.markdown("### Weekly Strength Pairs (based on Delta)")
        
        # We display the pairs in 2 columns (LF and AM only)
        p_col1, p_col2 = st.columns(2)
        
        categories_info = [
            ("Leveraged Funds", "LF", p_col1, ""),
            ("Asset Manager", "AM", p_col2, ""),
        ]
        
        for cat_label, cat_short, col, icon in categories_info:
            with col:
                pairs = calculate_strength_pairs(df_consolidated, cat_short)
                
                # HTML card container
                html_content = f"""
                <div style="
                    background: #ffffff;
                    padding: 1.2rem;
                    border-radius: 12px;
                    border: 1px solid rgba(99, 102, 241, 0.25);
                    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
                    margin-bottom: 1rem;
                ">
                    <h4 style="
                        color: #3730a3;
                        margin-top: 0;
                        margin-bottom: 15px;
                        font-size: 1.05rem;
                        font-weight: 700;
                        border-bottom: 1px solid rgba(99, 102, 241, 0.2);
                        padding-bottom: 8px;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                    ">
                        {cat_label} ({cat_short})
                    </h4>
                    <div style="display: flex; flex-direction: column; gap: 10px;">
                """
                
                if pairs:
                    ranks = ["S1", "S2", "S3", "S4"]
                    for idx, (strong, weak, s_val, w_val) in enumerate(pairs):
                        rank = ranks[idx] if idx < len(ranks) else str(idx + 1)
                        diff = s_val - w_val
                        s_name = clean_currency_name(strong)
                        w_name = clean_currency_name(weak)
                        
                        html_content += f"""
                        <div style="
                            display: flex;
                            justify-content: space-between;
                            align-items: center;
                            font-size: 0.9rem;
                            padding: 4px 0;
                            color: #1e1b4b;
                        ">
                            <span>
                                <b style="color:#4338ca;">[{rank}]</b> <b>{s_name}</b> vs <b>{w_name}</b>
                                <span style="color: #6b7280; font-size: 0.8rem; margin-left: 4px;">
                                    ({s_val:+.2f}% / {w_val:+.2f}%)
                                </span>
                            </span>
                            <span style="
                                color: #16a34a;
                                font-weight: 700;
                                background: rgba(22, 163, 74, 0.1);
                                padding: 2px 8px;
                                border-radius: 6px;
                                font-size: 0.85rem;
                                border: 1px solid rgba(22, 163, 74, 0.25);
                            ">
                                +{diff:.2f}%
                            </span>
                        </div>
                        """
                else:
                    html_content += """
                    <div style="color: #64748b; font-size: 0.9rem; font-style: italic; text-align: center; padding: 10px 0;">
                        No pairs available
                    </div>
                    """
                
                html_content += """
                    </div>
                </div>
                """
                st.markdown(clean_html_string(html_content), unsafe_allow_html=True)

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
            with st.expander(f"Report Date: {d}", expanded=(idx == 0)):
                # Extract cross-section for this date
                df_date = df_history.xs(d, level="Report Date")
                styled_history = format_historical_dataframe(df_date)
                st.dataframe(styled_history, use_container_width=True)

                if not df_lf_history.empty and d in df_lf_history.index.get_level_values("Report Date"):
                    st.markdown("#### Leveraged Funds Breakdown")
                    df_date_lf = df_lf_history.xs(d, level="Report Date")
                    styled_date_lf = format_lf_detail_dataframe(df_date_lf)
                    st.dataframe(styled_date_lf, use_container_width=True)


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

