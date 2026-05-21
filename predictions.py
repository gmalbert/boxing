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
from data.db import Fight, Fighter, OddsSnapshot, get_session, get_upcoming_fights
from footer import add_betting_oracle_footer
from pathlib import Path
from models import logistic_model as lm
from utils.odds_utils import fmt_american

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

def _home_win_pct(fighter: Fighter) -> float:
    total = (fighter.wins or 0) + (fighter.losses or 0)
    return (fighter.wins / total) if total else 0.5


def _home_ko_pct(fighter: Fighter) -> float:
    wins = fighter.wins or 0
    return (fighter.ko_wins or 0) / wins if wins else 0.0


def _home_fight_features(fighter_a: Fighter, fighter_b: Fighter) -> dict:
    return {
        "reach_diff": 0,
        "height_diff": 0,
        "age_diff": 0,
        "win_pct_diff": _home_win_pct(fighter_a) - _home_win_pct(fighter_b),
        "ko_pct_diff": _home_ko_pct(fighter_a) - _home_ko_pct(fighter_b),
        "elo_diff": (fighter_a.elo_rating or 1500) - (fighter_b.elo_rating or 1500),
        "days_since_last_fight_diff": 0,
        "opposition_quality_diff": 0,
        "is_southpaw_matchup": int(
            (fighter_a.stance or "").lower() != (fighter_b.stance or "").lower()
        ),
    }


def _home_fighter_label(name: str, prob: float, odds: int | None) -> str:
    label = f"{name} ({prob:.0%})"
    if odds is not None:
        label += f" ({fmt_american(odds)})"
    return label


@st.cache_data(ttl=120, show_spinner=False)
def load_home_upcoming_fights(limit: int = 4) -> list[dict]:
    session = get_session()
    try:
        fights = get_upcoming_fights(session)[:limit]
        rows = []
        for fight in fights:
            boxer_a = session.get(Fighter, fight.fighter_a_id)
            boxer_b = session.get(Fighter, fight.fighter_b_id)
            if not boxer_a or not boxer_b:
                continue

            snaps = (
                session.query(OddsSnapshot)
                .filter(OddsSnapshot.fight_id == fight.id)
                .order_by(OddsSnapshot.snapshot_time.desc())
                .limit(50)
                .all()
            )
            odds_a = _extract_dk_odds(snaps, boxer_a.name)
            odds_b = _extract_dk_odds(snaps, boxer_b.name)

            features = _home_fight_features(boxer_a, boxer_b)
            prob_a = lm.predict_proba(features)
            prob_b = 1 - prob_a

            rows.append({
                "fighter_a": boxer_a.name,
                "fighter_b": boxer_b.name,
                "prob_a": prob_a,
                "prob_b": prob_b,
                "odds_a": odds_a,
                "odds_b": odds_b,
                "weight_class": fight.weight_class or "",
                "date": fight.fight_date.strftime("%b %d") if fight.fight_date else "",
                "title_fight": fight.title_fight,
            })
        return rows
    finally:
        session.close()


@st.cache_data(ttl=120, show_spinner=False)
def _extract_dk_odds(_snaps: list, fighter_name: str) -> int | None:
    for s in _snaps:
        if s.bookmaker == "draftkings" and s.fighter_name == fighter_name:
            return s.american_odds
    return None


def home_page():
    """Dashboard landing page."""

    # ── Logo + Hero header ────────────────────────────────────────────────
    if _LOGO_PATH.exists():
        logo_col, title_col = st.columns([1, 5])
        with logo_col:
            st.image(str(_LOGO_PATH), width="stretch")
        with title_col:
            st.markdown(
                f"<h1 style='font-size:2.8rem;margin-bottom:0;padding-top:0.4rem'>"
                f"{APP_SUBTITLE}"
                f"</h1>"
                # f"<p style='color:#9ca3af;font-size:1.1rem;margin-top:4px'>"
                # f"{APP_SUBTITLE}"
                # f"</p>"
                ,
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

    upcoming_fights = load_home_upcoming_fights()

    with st.container(border=True):
        st.markdown("### 🔥 Upcoming Matches")
        if not upcoming_fights:
            st.info("No upcoming fights are currently available.", icon="ℹ️")
        else:
            for fight in upcoming_fights:
                title_flag = " 🏆" if fight["title_fight"] else ""
                a_label = _home_fighter_label(fight["fighter_a"], fight["prob_a"], fight["odds_a"])
                b_label = _home_fighter_label(fight["fighter_b"], fight["prob_b"], fight["odds_b"])
                details = " · ".join(
                    part for part in [fight["date"], fight["weight_class"]] if part
                )
                if details:
                    st.markdown(
                        f"**{a_label} vs {b_label}**{title_flag}<br>"
                        f"{details}",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"**{a_label} vs {b_label}**{title_flag}",
                        unsafe_allow_html=True,
                    )
            st.caption("These are the next scheduled fights in your database.")
        if st.button("View Fight Card", key="home_fc"):
            st.switch_page("pages/01_Fight_Card.py")

    st.markdown("---")
    st.markdown("### Quick links")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Fight Card", key="home_fc2"):
            st.switch_page("pages/01_Fight_Card.py")
    with c2:
        if st.button("Model Dashboard", key="home_md2"):
            st.switch_page("pages/05_Model_Dashboard.py")
    with c3:
        if st.button("Fight Database", key="home_fd2"):
            st.switch_page("pages/07_Fight_Database.py")
    st.markdown("---")

    # ── How This Works ────────────────────────────────────────────────────────
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

    with st.expander("⚙️ Setup Status", expanded=False):
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
