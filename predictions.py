"""
KnockOutIQ — Entry Point (predictions.py)
Boxing data analytics & betting intelligence platform.

Run with:
    streamlit run predictions.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from config import APP_ICON, APP_TITLE, APP_SUBTITLE
from footer import add_betting_oracle_footer
from pathlib import Path

_LOGO_PATH = Path(__file__).parent / "data_files" / "logo.png"

# ─── Page Config (called ONCE here — sub-pages must NOT call set_page_config) ─
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "https://github.com/gmalbert/boxing",
        "Report a bug": "https://github.com/gmalbert/boxing/issues",
        "About": f"**{APP_TITLE}** — {APP_SUBTITLE}",
    },
)

# ─── Adaptive Theme CSS (Arctic White / Slate via prefers-color-scheme) ───────
st.markdown("""
<style>
/* ╔═══════════════════════════════════════════════════════════════════
   KnockOutIQ — Auto-adaptive theme
   ☀️  Arctic White  (prefers-color-scheme: light)
   🌙  Slate          (prefers-color-scheme: dark)
   ╚═══════════════════════════════════════════════════════════════════ */

/* ── Shared structure (theme-agnostic) ─────────────────────────────── */
[data-testid="stSidebarNav"] a { padding: 0.35rem 0.75rem; border-radius: 6px; }
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 10px; }
[data-testid="stMetric"] { border-radius: 8px; padding: 8px 12px; }
[data-testid="stMetricLabel"] { font-size: 0.78rem; }
[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
[data-testid="stPlotlyChart"] { border-radius: 8px; }
[data-testid="stSidebar"] img { border-radius: 10px; margin: 6px 0; width: 100%; }

/* ╔═══════════════════════════════════════════════════════════════════
   ☀️  ARCTIC WHITE — light mode
   ╚═══════════════════════════════════════════════════════════════════ */
@media (prefers-color-scheme: light) {
    /* Backgrounds */
    [data-testid="stApp"],[data-testid="stAppViewContainer"],
    section[data-testid="stMain"],.stMainBlockContainer
    { background-color: #f0f4f8 !important; }
    [data-testid="stHeader"],header[data-testid="stHeader"],[data-testid="stToolbar"]
    { background-color: #d9e8f1 !important; border-bottom: 1px solid #90b8d0 !important; }
    [data-testid="stSidebar"],[data-testid="stSidebar"] > div:first-child
    { background-color: #e2ecf3 !important; }
    /* Text */
    body,html,.stMarkdown,.stMarkdown p,.stMarkdown li,
    h1,h2,h3,h4,h5,h6,[data-testid="stText"],
    [data-testid="stSidebar"] span,[data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label
    { color: #1e2f3d !important; }
    [data-testid="stMarkdownContainer"] h1,[data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3 { color: #1e2f3d !important; }
    [data-testid="stCaptionContainer"],.stCaption,small { color: #4a6a80 !important; }
    /* Metrics */
    [data-testid="stMetric"] { background-color: #d9e8f1 !important; border: 1px solid #90b8d0 !important; }
    [data-testid="stMetricLabel"] { color: #4a6a80 !important; }
    [data-testid="stMetricValue"] { color: #1e2f3d !important; }
    /* Buttons */
    .stButton > button { background-color: #0369a1 !important; border-color: #0369a1 !important; color: #fff !important; }
    .stButton > button:hover { opacity: 0.85; }
    /* Containers */
    [data-testid="stVerticalBlockBorderWrapper"] { background-color: #d9e8f1 !important; border-color: #90b8d0 !important; }
    /* Inputs */
    .stTextInput input,.stNumberInput input,
    div[data-baseweb="input"] input,div[data-baseweb="textarea"] textarea
    { background-color: #fff !important; border-color: #90b8d0 !important; color: #1e2f3d !important; }
    div[data-baseweb="select"] > div,div[data-baseweb="popover"]
    { background-color: #fff !important; border-color: #90b8d0 !important; color: #1e2f3d !important; }
    /* AG Grid / DataFrames */
    .ag-root-wrapper { background-color: #f0f4f8 !important; border-color: #90b8d0 !important; }
    .ag-header,.ag-header-row { background-color: #cddce9 !important; border-bottom-color: #90b8d0 !important; }
    .ag-header-cell,.ag-header-cell-text { color: #1e2f3d !important; background-color: #cddce9 !important; }
    .ag-row { background-color: #f0f4f8 !important; color: #1e2f3d !important; border-bottom-color: #d0dde8 !important; }
    .ag-row-even { background-color: #e8f0f7 !important; }
    .ag-row:hover,.ag-row-hover { background-color: #d9e8f1 !important; }
    .ag-cell,.ag-cell-value { color: #1e2f3d !important; border-right-color: #d0dde8 !important; }
    /* Plotly — transparent SVG so container color shows; recolor text/grid */
    [data-testid="stPlotlyChart"] { background-color: #e4eff7 !important; }
    [data-testid="stPlotlyChart"] .main-svg,[data-testid="stPlotlyChart"] .main-svg .bg { fill: transparent !important; }
    [data-testid="stPlotlyChart"] text { fill: #1e2f3d !important; }
    [data-testid="stPlotlyChart"] .gridlayer path,[data-testid="stPlotlyChart"] .gridlayer line { stroke: #90b8d0 !important; stroke-opacity:0.7; }
    [data-testid="stPlotlyChart"] .zerolinelayer path { stroke: #4a6a80 !important; }
    /* Tabs */
    [data-baseweb="tab-list"] { background-color: transparent !important; border-bottom: 2px solid #90b8d0 !important; }
    [data-baseweb="tab"] { color: #4a6a80 !important; }
    [data-baseweb="tab"][aria-selected="true"] { color: #0369a1 !important; border-bottom-color: #0369a1 !important; }
    /* Expanders */
    [data-testid="stExpander"] { background-color: #d9e8f1 !important; border-color: #90b8d0 !important; }
    [data-testid="stExpander"] summary p { color: #1e2f3d !important; }
    /* Misc */
    hr { border-color: #90b8d0 !important; }
    [data-testid="stSidebarNav"] a:hover { background: rgba(3,105,161,0.12); }
    [data-testid="stSidebarNav"] a span { color: #1e2f3d !important; }
    [data-testid="stCheckbox"] label { color: #1e2f3d !important; }
    [data-testid="stAlert"] { border-radius: 8px; }
}

/* ╔═══════════════════════════════════════════════════════════════════
   🌙  SLATE — dark mode
   ╚═══════════════════════════════════════════════════════════════════ */
@media (prefers-color-scheme: dark) {
    /* Backgrounds */
    [data-testid="stApp"],[data-testid="stAppViewContainer"],
    section[data-testid="stMain"],.stMainBlockContainer
    { background-color: #1e293b !important; }
    [data-testid="stHeader"],header[data-testid="stHeader"],[data-testid="stToolbar"]
    { background-color: #1a2333 !important; border-bottom: 1px solid #475569 !important; }
    [data-testid="stSidebar"],[data-testid="stSidebar"] > div:first-child
    { background-color: #263247 !important; }
    /* Text */
    body,html,.stMarkdown,.stMarkdown p,.stMarkdown li,
    h1,h2,h3,h4,h5,h6,[data-testid="stText"],
    [data-testid="stSidebar"] span,[data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label
    { color: #e2e8f0 !important; }
    [data-testid="stMarkdownContainer"] h1,[data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3 { color: #e2e8f0 !important; }
    [data-testid="stCaptionContainer"],.stCaption,small { color: #94a3b8 !important; }
    /* Metrics */
    [data-testid="stMetric"] { background-color: #2d3d52 !important; border: 1px solid #475569 !important; }
    [data-testid="stMetricLabel"] { color: #94a3b8 !important; }
    [data-testid="stMetricValue"] { color: #e2e8f0 !important; }
    /* Buttons */
    .stButton > button { background-color: #475569 !important; border-color: #475569 !important; color: #fff !important; }
    .stButton > button:hover { opacity: 0.85; }
    /* Containers */
    [data-testid="stVerticalBlockBorderWrapper"] { background-color: #2d3d52 !important; border-color: #475569 !important; }
    /* Inputs */
    .stTextInput input,.stNumberInput input,
    div[data-baseweb="input"] input,div[data-baseweb="textarea"] textarea
    { background-color: #2d3d52 !important; border-color: #475569 !important; color: #e2e8f0 !important; }
    div[data-baseweb="select"] > div,div[data-baseweb="popover"]
    { background-color: #2d3d52 !important; border-color: #475569 !important; color: #e2e8f0 !important; }
    /* AG Grid / DataFrames */
    .ag-root-wrapper { background-color: #1e293b !important; border-color: #475569 !important; }
    .ag-header,.ag-header-row { background-color: #334155 !important; border-bottom-color: #475569 !important; }
    .ag-header-cell,.ag-header-cell-text { color: #e2e8f0 !important; background-color: #334155 !important; }
    .ag-row { background-color: #1e293b !important; color: #e2e8f0 !important; border-bottom-color: #2d3d52 !important; }
    .ag-row-even { background-color: #253145 !important; }
    .ag-row:hover,.ag-row-hover { background-color: #2d3d52 !important; }
    .ag-cell,.ag-cell-value { color: #e2e8f0 !important; border-right-color: #2d3d52 !important; }
    /* Plotly — transparent SVG so container color shows; recolor text/grid */
    [data-testid="stPlotlyChart"] { background-color: #243040 !important; }
    [data-testid="stPlotlyChart"] .main-svg,[data-testid="stPlotlyChart"] .main-svg .bg { fill: transparent !important; }
    [data-testid="stPlotlyChart"] text { fill: #e2e8f0 !important; }
    [data-testid="stPlotlyChart"] .gridlayer path,[data-testid="stPlotlyChart"] .gridlayer line { stroke: #475569 !important; stroke-opacity:0.6; }
    [data-testid="stPlotlyChart"] .zerolinelayer path { stroke: #94a3b8 !important; }
    /* Tabs */
    [data-baseweb="tab-list"] { background-color: transparent !important; border-bottom: 2px solid #475569 !important; }
    [data-baseweb="tab"] { color: #94a3b8 !important; }
    [data-baseweb="tab"][aria-selected="true"] { color: #e2e8f0 !important; border-bottom-color: #94a3b8 !important; }
    /* Expanders */
    [data-testid="stExpander"] { background-color: #2d3d52 !important; border-color: #475569 !important; }
    [data-testid="stExpander"] summary p { color: #e2e8f0 !important; }
    /* Misc */
    hr { border-color: #475569 !important; }
    [data-testid="stSidebarNav"] a:hover { background: rgba(148,163,184,0.15); }
    [data-testid="stSidebarNav"] a span { color: #e2e8f0 !important; }
    [data-testid="stCheckbox"] label { color: #e2e8f0 !important; }
    [data-testid="stAlert"] { border-radius: 8px; }
}
</style>
""", unsafe_allow_html=True)


# ─── Home Page Content ────────────────────────────────────────────────────────

def home_page():
    """Dashboard landing page."""

    # ── Logo + Hero header ────────────────────────────────────────────────
    if _LOGO_PATH.exists():
        logo_col, title_col = st.columns([1, 5])
        with logo_col:
            st.image(str(_LOGO_PATH), use_container_width=True)
        with title_col:
            st.markdown(
                f"<h1 style='font-size:2.8rem;margin-bottom:0;padding-top:0.4rem'>"
                f"{APP_TITLE}"
                f"</h1>"
                f"<p style='color:#9ca3af;font-size:1.1rem;margin-top:4px'>"
                f"{APP_SUBTITLE}"
                f"</p>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            f"<h1 style='font-size:2.8rem;margin-bottom:0'>"
            f"{APP_ICON} {APP_TITLE}"
            f"</h1>"
            f"<p style='color:#9ca3af;font-size:1.1rem;margin-top:4px'>"
            f"{APP_SUBTITLE}"
            f"</p>",
            unsafe_allow_html=True,
        )
    st.markdown("---")

    # Quick-nav cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        with st.container(border=True):
            st.markdown("### 📅 Fight Card")
            st.caption("Upcoming fights with DraftKings odds and model edge signals.")
            if st.button("Go to Fight Card", key="nav_fc"):
                st.switch_page("pages/01_Fight_Card.py")
    with col2:
        with st.container(border=True):
            st.markdown("### 🥊 Fighter Profiles")
            st.caption("Career records, Elo ratings, punch stats, and style breakdowns.")
            if st.button("Go to Fighter Profile", key="nav_fp"):
                st.switch_page("pages/02_Fighter_Profile.py")
    with col3:
        with st.container(border=True):
            st.markdown("### ⚔️ Matchup Analyzer")
            st.caption("Head-to-head fighter comparison with win probability and style matchup.")
            if st.button("Go to Matchup Analyzer", key="nav_ma"):
                st.switch_page("pages/03_Matchup_Analyzer.py")
    with col4:
        with st.container(border=True):
            st.markdown("### 📈 Odds Tracker")
            st.caption("DraftKings vs. Pinnacle line movement and sharp money signals.")
            if st.button("Go to Odds Tracker", key="nav_ot"):
                st.switch_page("pages/04_Odds_Tracker.py")

    col5, col6, col7, _ = st.columns(4)
    with col5:
        with st.container(border=True):
            st.markdown("### 🤖 Model Dashboard")
            st.caption("All upcoming fights ranked by edge magnitude.")
            if st.button("Go to Model Dashboard", key="nav_md"):
                st.switch_page("pages/05_Model_Dashboard.py")
    with col6:
        with st.container(border=True):
            st.markdown("### 💰 Bet Tracker")
            st.caption("Log bets, track CLV, and measure long-run edge.")
            if st.button("Go to Bet Tracker", key="nav_bt"):
                st.switch_page("pages/06_Bet_Tracker.py")
    with col7:
        with st.container(border=True):
            st.markdown("### 📚 Fight Database")
            st.caption("Search 10 years of boxing history with trends and analytics.")
            if st.button("Go to Fight Database", key="nav_fd"):
                st.switch_page("pages/07_Fight_Database.py")

    st.markdown("---")

    # ── How This Works ─────────────────────────────────────────────────────
    with st.expander("📖 How KnockOutIQ Works", expanded=False):
        st.markdown("""
**KnockOutIQ** uses a three-layer approach to find value in boxing betting markets:

1. **Data Layer** — Pulls fighter profiles, fight history, and CompuBox punch stats from
   boxing-data.com (via RapidAPI), live DraftKings moneylines from The Odds API,
   and Pinnacle reference lines from OddsPapi.

2. **Model Layer** — Two prediction models:
   - *Logistic Regression* — interpretable baseline using reach, age, win%, KO%, Elo differential
   - *XGBoost Ensemble* — primary model with rolling form features and style matchup encoding

   Both models are supplemented by a dynamic **Elo rating system** that captures fighter
   trajectory better than raw win percentage.

3. **Edge Detection** — Edge = `Model Probability − DK Implied Probability`.
   A positive edge means the model believes DraftKings is mispricing the fight.
   Pinnacle's (the sharpest book) line is used as a secondary reference.

**Closing Line Value (CLV)** is tracked for every logged bet — if you consistently beat
the closing line, you're making +EV decisions regardless of short-term results.

> *All content is for informational purposes only. Wager responsibly.*
        """)

    # ── Setup Status ───────────────────────────────────────────────────────
    _show_setup_status()

    add_betting_oracle_footer()


def _show_setup_status():
    """Quick status check on API keys and database."""
    from config import RAPID_API_KEY, ODDS_API_KEY, ODDSPAPI_KEY, DB_PATH

    st.markdown("### ⚙️ Setup Status")
    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "boxing-data.com",
        "✅ Connected" if RAPID_API_KEY else "⚠️ No Key",
        help="RapidAPI key for fighter profiles & fight history",
    )
    c2.metric(
        "The Odds API",
        "✅ Connected" if ODDS_API_KEY else "⚠️ No Key",
        help="DraftKings & multi-book odds",
    )
    c3.metric(
        "OddsPapi",
        "✅ Connected" if ODDSPAPI_KEY else "⚠️ No Key",
        help="Pinnacle sharp reference lines",
    )
    c4.metric(
        "Database",
        "✅ Ready" if DB_PATH.exists() else "📭 Empty",
        help="SQLite database at data_files/knockoutiq.db",
    )

    if not any([RAPID_API_KEY, ODDS_API_KEY, ODDSPAPI_KEY]):
        st.warning(
            "No API keys detected. Add them to your `.env` file — "
            "see `.env.example` for the required variables.",
            icon="⚠️",
        )
    elif not DB_PATH.exists() or DB_PATH.stat().st_size < 10_000:
        st.info(
            "Database is empty. Run the historical data backfill to populate it:\n"
            "```\npython scripts/fetch_historical_data.py backfill\n```",
            icon="ℹ️",
        )


# ─── Navigation ───────────────────────────────────────────────────────────────

pg = st.navigation(
    {
        "": [
            st.Page(home_page, title="Home", icon="🏠", default=True),
        ],
        "Fight Analysis": [
            st.Page("pages/01_Fight_Card.py",       title="Fight Card",        icon="📅"),
            st.Page("pages/02_Fighter_Profile.py",  title="Fighter Profile",   icon="🥊"),
            st.Page("pages/03_Matchup_Analyzer.py", title="Matchup Analyzer",  icon="⚔️"),
            st.Page("pages/04_Odds_Tracker.py",     title="Odds Tracker",      icon="📈"),
        ],
        "Models & Betting": [
            st.Page("pages/05_Model_Dashboard.py",  title="Model Dashboard",   icon="🤖"),
            st.Page("pages/06_Bet_Tracker.py",      title="Bet Tracker & CLV", icon="💰"),
        ],
        "Data": [
            st.Page("pages/07_Fight_Database.py",   title="Fight Database",    icon="📚"),
        ],
    }
)

pg.run()
