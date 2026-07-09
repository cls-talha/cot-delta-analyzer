"""
COT Analyzer Dashboard — Streamlit Application.

Displays CFTC Commitments of Traders data for Leveraged Funds,
Asset Managers, and Dealers across major currencies and indices.
Single-page layout with Plotly graphs and historical tables.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

from cot_fetcher import fetch_current_week, fetch_archive_week, get_recent_release_dates
from cot_parser import parse_report
from cot_calculator import compute_consolidated_table, compute_historical_table, CATEGORY_SHORT
from config import get_archive_url

# ──────────────────────────────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="COT Analyzer Dashboard",
    page_icon="📊",
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
    text-align: right !important;
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
@st.cache_data(ttl=3600, show_spinner=False)
def load_current_data():
    """Fetch and parse current week data (cached 1 hour)."""
    raw = fetch_current_week()
    if raw is None:
        return None
    return parse_report(raw)


@st.cache_data(ttl=3600, show_spinner=False)
def load_archive_data(release_date_str: str):
    """Fetch and parse archive week data (cached 1 hour)."""
    from datetime import date
    parts = release_date_str.split("-")
    d = date(int(parts[0]), int(parts[1]), int(parts[2]))
    raw = fetch_archive_week(d)
    if raw is None:
        return None
    return parse_report(raw)


def style_delta(val):
    """Apply red/green styling to delta values."""
    if pd.isna(val) or val is None:
        return "color: #64748b"
    if val > 0:
        return "color: #4ade80; font-weight: 600"
    elif val < 0:
        return "color: #f87171; font-weight: 600"
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
        styled = styled.map(style_delta, subset=delta_cols)

    # Style the rest
    styled = styled.set_properties(**{
        "text-align": "right",
        "font-size": "0.85rem",
    })

    return styled


def format_historical_dataframe(df: pd.DataFrame):
    """Apply formatting to the historical DataFrame."""
    format_dict = {}
    for col in df.columns:
        if "Net Pos" in col:
            format_dict[col] = "{:,.0f}"
        elif "Net %" in col:
            format_dict[col] = "{:.2f}%"
            
    styled = df.style.format(format_dict, na_rep="—")
    styled = styled.set_properties(**{
        "text-align": "right",
        "font-size": "0.85rem",
    })
    return styled


# ──────────────────────────────────────────────────────────────────────
# Main App
# ──────────────────────────────────────────────────────────────────────
def main():
    # ── Header ──
    st.markdown("""
    <div class="main-header">
        <h1>📊 COT Analyzer Dashboard</h1>
        <div class="subtitle">
            Commitments of Traders — Financial Futures (Futures Only)
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ── Controls & Status Row ──
    recent_dates = get_recent_release_dates(count=4)
    
    col1, col2, col3, col4 = st.columns([2, 3, 3, 4])
    with col1:
        if st.button("🔄 Refresh Data", use_container_width=True, type="primary"):
            st.cache_data.clear()
            st.rerun()
            
    with col2:
        if len(recent_dates) > 0:
            st.markdown(
                f'<div class="date-badge">📌 Current: {recent_dates[0].strftime("%b %d, %Y")}</div>',
                unsafe_allow_html=True,
            )
            
    with col3:
        if len(recent_dates) > 1:
            st.markdown(
                f'<div class="date-badge">📎 Previous: {recent_dates[1].strftime("%b %d, %Y")}</div>',
                unsafe_allow_html=True,
            )
            
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Load Data ──
    reports_data = []
    
    with st.spinner("🔄 Fetching data from CFTC..."):
        if len(recent_dates) > 0:
            current = load_current_data()
            if current:
                reports_data.append(current)
            else:
                st.error("⚠️ Failed to fetch current week data.")
                return
                
        # Fetch up to 3 previous weeks
        for archive_date in recent_dates[1:]:
            arch = load_archive_data(archive_date.isoformat())
            if arch:
                reports_data.append(arch)

    if not reports_data:
        st.error("⚠️ No data available.")
        return

    current_data = reports_data[0]
    previous_data = reports_data[1] if len(reports_data) > 1 else None

    # ── Consolidated Table (Current Week) ──
    st.markdown("### 📅 Current Week Overview")
    df_consolidated = compute_consolidated_table(current_data, previous_data)
    
    if not df_consolidated.empty:
        styled_consolidated = format_consolidated_dataframe(df_consolidated)
        st.dataframe(
            styled_consolidated,
            use_container_width=True,
            height=430,
        )
    else:
        st.warning("No data found for current week.")

    st.markdown("<hr style='border: 1px solid rgba(255,255,255,0.05); margin: 2rem 0;'>", unsafe_allow_html=True)

    # ── Plotly Graphs ──
    if not df_consolidated.empty and previous_data:
        st.markdown("### 📈 Weekly Delta Visualization (%)")
        
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
    st.markdown(f"### 🕰️ Historical Data (Last {len(reports_data)} Reports)")
    df_history = compute_historical_table(reports_data)
    
    if not df_history.empty:
        # df_history has a MultiIndex: ["Currency", "Report Date"]
        # We extract unique dates (they preserve order from reports_data)
        dates = df_history.index.get_level_values("Report Date").unique()
        
        for d in dates:
            with st.expander(f"Report Date: {d}", expanded=True):
                # Extract cross-section for this date
                df_date = df_history.xs(d, level="Report Date")
                styled_history = format_historical_dataframe(df_date)
                st.dataframe(
                    styled_history,
                    use_container_width=True,
                )

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

# there are 3 extra rows in streamlit can you remove it also we have full year release date of cot report  if you dont have here it is

# Month	Dates
# January	05*	09	16	23	30
# February	06	13	20	27	 
# March	06	13	20	27	 
# April	03	10	17	24	 
# May	01	08	15	22	29
# June 	05	12	22*	26	 
# July	06*	10	17	24	31
# August	07	14	21	28	 
# September	04	11	18	25	 
# October	02	09	16	23	30
# November	06	16*	20	30*	 
# December	04	11	18	28*	 


# as of now, we have 3-4 week hisotry in webapp, i want delta highlight color as well as red of green for hisotrical do it for full year,, also base on delta give pairs as well, like strongest vs weakest and 2nd strong vs 1st weakest etc and no repeating pairs, right above graph and below table
