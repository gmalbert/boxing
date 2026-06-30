"""
KnockOutIQ — Fight Card Page
Upcoming fights with current DraftKings odds and model edge indicators.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import ODDS_API_KEY
from data.db import Fight, Fighter, OddsSnapshot, get_session
from utils.odds_utils import (
    american_to_implied_prob,
    calculate_edge,
    edge_label,
    fmt_american,
    no_vig_prob_from_american,
)
import models.logistic_model as lm
import models.xgboost_model as xgb
from utils.page_utils import sidebar_header


# ─── Data Loaders ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def load_upcoming_fights() -> list[dict]:
    """Load upcoming fights with fighter data and latest odds."""
    session = get_session()
    try:
        fights = (
            session.query(Fight)
            .filter(Fight.is_upcoming == True)
            .order_by(Fight.fight_date)
            .all()
        )
        rows = []
        for fight in fights:
            fa = session.get(Fighter, fight.fighter_a_id)
            fb = session.get(Fighter, fight.fighter_b_id)
            if not fa or not fb:
                continue

            # Skip women's bouts
            if getattr(fa, 'sex', 'M') == 'F' or getattr(fb, 'sex', 'M') == 'F':
                continue
            snaps = (
                session.query(OddsSnapshot)
                .filter(
                    OddsSnapshot.fight_id == fight.id,
                    OddsSnapshot.bookmaker == "draftkings",
                )
                .order_by(OddsSnapshot.snapshot_time.desc())
                .all()
            )
            dk_odds_a = _extract_dk_odds(snaps, fa.name)
            dk_odds_b = _extract_dk_odds(snaps, fb.name)

            rows.append({
                "fight_id": fight.id,
                "fight_date": fight.fight_date,
                "event_name": fight.event_name or "",
                "weight_class": fight.weight_class or "N/A",
                "title_fight": fight.title_fight,
                "total_rounds": fight.total_rounds or 12,
                "fighter_a_id": fa.id,
                "fighter_a": fa.name,
                "fighter_a_record": f"{fa.wins}-{fa.losses}-{fa.draws}",
                "fighter_a_elo": fa.elo_rating or 1500,
                "fighter_a_ko_pct": _ko_pct(fa),
                "fighter_a_stance": fa.stance or "Orthodox",
                "fighter_b_id": fb.id,
                "fighter_b": fb.name,
                "fighter_b_record": f"{fb.wins}-{fb.losses}-{fb.draws}",
                "fighter_b_elo": fb.elo_rating or 1500,
                "fighter_b_ko_pct": _ko_pct(fb),
                "fighter_b_stance": fb.stance or "Orthodox",
                "dk_odds_a": dk_odds_a,
                "dk_odds_b": dk_odds_b,
            })
        return rows
    finally:
        session.close()


def _extract_dk_odds(snaps: list, fighter_name: str) -> int | None:
    for s in snaps:
        if s.bookmaker == "draftkings" and s.fighter_name == fighter_name:
            return s.american_odds
    return None


def _ko_pct(fighter: Fighter) -> float:
    total_wins = fighter.wins or 0
    ko_wins = fighter.ko_wins or 0
    if total_wins == 0:
        return 0.0
    return ko_wins / total_wins


def _model_features(row: dict) -> dict:
    return {
        "reach_diff": 0,
        "height_diff": 0,
        "age_diff": 0,
        "win_pct_diff": _win_pct(row, "a") - _win_pct(row, "b"),
        "ko_pct_diff": row["fighter_a_ko_pct"] - row["fighter_b_ko_pct"],
        "elo_diff": row["fighter_a_elo"] - row["fighter_b_elo"],
        "days_since_last_fight_diff": 0,
        "opposition_quality_diff": 0,
        "is_southpaw_matchup": int(
            (row["fighter_a_stance"] or "").lower() != (row["fighter_b_stance"] or "").lower()
        ),
    }


def _win_pct(row: dict, side: str) -> float:
    w = row.get(f"fighter_{side}_record", "0-0-0").split("-")
    try:
        wins, losses = int(w[0]), int(w[1])
        total = wins + losses
        return wins / total if total > 0 else 0.5
    except Exception:
        return 0.5


# ─── Sparkline ────────────────────────────────────────────────────────────────

def _odds_sparkline(fight_id: int, fighter_name: str) -> go.Figure:
    session = get_session()
    try:
        snaps = (
            session.query(OddsSnapshot)
            .filter(
                OddsSnapshot.fight_id == fight_id,
                OddsSnapshot.bookmaker == "draftkings",
                OddsSnapshot.fighter_name == fighter_name,
            )
            .order_by(OddsSnapshot.snapshot_time)
            .all()
        )
        times = [s.snapshot_time for s in snaps]
        odds_vals = [s.american_odds for s in snaps]
    finally:
        session.close()

    fig = go.Figure(go.Scatter(
        x=times, y=odds_vals, mode="lines",
        line=dict(color="#3b82f6", width=2),
    ))
    fig.update_layout(
        height=60, margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ─── Page ─────────────────────────────────────────────────────────────────────

def fight_card_page():
    sidebar_header()
    st.title("📅 Fight Card")
    st.caption("Upcoming bouts · DraftKings odds · Model edge signals")

    # Refresh button
    col_refresh, col_spacer = st.columns([1, 5])
    with col_refresh:
        if st.button("🔄 Refresh Odds"):
            st.cache_data.clear()
            st.rerun()

    fights = load_upcoming_fights()

    if not fights:
        st.info(
            "No upcoming fights loaded yet. "
            "Run `python scripts/fetch_historical_data.py daily` to pull the latest schedule and odds.",
            icon="ℹ️",
        )
        _demo_fight_card()
        return

    # ── Filters ────────────────────────────────────────────────────────────
    weight_classes = sorted({f["weight_class"] for f in fights if f["weight_class"] != "N/A"})
    col_wc, col_title = st.columns(2)
    with col_wc:
        selected_wc = st.multiselect("Weight Class", weight_classes, default=[])
    with col_title:
        title_only = st.checkbox("Title Fights Only", value=False)

    filtered = fights
    if selected_wc:
        filtered = [f for f in filtered if f["weight_class"] in selected_wc]
    if title_only:
        filtered = [f for f in filtered if f["title_fight"]]

    if not filtered:
        st.warning("No fights match your filters.")
        return

    st.markdown(f"**{len(filtered)} upcoming fight(s)**")

    for row in filtered:
        _render_fight_card(row)


def _render_fight_card(row: dict):
    """Render a single fight card with odds and model probability."""
    # Compute model probability
    features = _model_features(row)
    model_prob_a = lm.predict_proba(features)
    model_prob_b = 1 - model_prob_a

    # Edge vs DK
    edge_a = None
    if row["dk_odds_a"] is not None:
        edge_a = calculate_edge(model_prob_a, row["dk_odds_a"])

    label, color = edge_label(edge_a or 0)

    with st.container(border=True):
        # Header row
        h_col1, h_col2, h_col3 = st.columns([3, 1, 3])
        with h_col1:
            st.markdown(f"### {row['fighter_a']}")
            st.caption(row["fighter_a_record"])
        with h_col2:
            date_str = row["fight_date"].strftime("%b %d") if row["fight_date"] else "TBD"
            st.markdown(f"<div style='text-align:center; padding-top:10px'><b>{date_str}</b><br>{row['weight_class']}</div>",
                        unsafe_allow_html=True)
            if row["title_fight"]:
                st.markdown("<div style='text-align:center'>🏆</div>", unsafe_allow_html=True)
        with h_col3:
            st.markdown(f"### {row['fighter_b']}")
            st.caption(row["fighter_b_record"])

        # Odds + Model row
        m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns([2, 2, 1, 2, 2])
        with m_col1:
            st.metric("DK Odds", fmt_american(row["dk_odds_a"]))
        with m_col2:
            st.metric("Model Prob", f"{model_prob_a:.0%}")
        with m_col3:
            st.markdown(f"<div style='text-align:center;color:{color};font-size:20px;padding-top:14px'>{label[:2]}</div>",
                        unsafe_allow_html=True)
        with m_col4:
            st.metric("Model Prob", f"{model_prob_b:.0%}")
        with m_col5:
            st.metric("DK Odds", fmt_american(row["dk_odds_b"]))

        # Edge detail
        if edge_a is not None:
            st.markdown(f"**Edge on {row['fighter_a']}:** `{edge_a:+.1%}` — {label}")

        # Elo ratings
        e_col1, e_col2 = st.columns(2)
        with e_col1:
            st.caption(f"Elo: {row['fighter_a_elo']:.0f}  |  KO%: {row['fighter_a_ko_pct']:.0%}")
        with e_col2:
            st.caption(f"Elo: {row['fighter_b_elo']:.0f}  |  KO%: {row['fighter_b_ko_pct']:.0%}")


def _demo_fight_card():
    """Show a sample card when no real data is available."""
    st.markdown("---")
    st.markdown("#### Demo — Sample Fight Card")
    demo_rows = [
        {
            "fighter_a": "Canelo Álvarez", "fighter_a_record": "60-2-2",
            "fighter_a_elo": 1820, "fighter_a_ko_pct": 0.58, "fighter_a_stance": "Orthodox",
            "fighter_b": "Dmitry Bivol", "fighter_b_record": "23-1-0",
            "fighter_b_elo": 1790, "fighter_b_ko_pct": 0.52, "fighter_b_stance": "Orthodox",
            "fight_date": None, "weight_class": "Light Heavyweight",
            "title_fight": True, "total_rounds": 12,
            "dk_odds_a": -130, "dk_odds_b": 110,
        },
        {
            "fighter_a": "Terence Crawford", "fighter_a_record": "40-0-0",
            "fighter_a_elo": 1910, "fighter_a_ko_pct": 0.73, "fighter_a_stance": "Southpaw",
            "fighter_b": "Errol Spence Jr.", "fighter_b_record": "28-1-0",
            "fighter_b_elo": 1850, "fighter_b_ko_pct": 0.68, "fighter_b_stance": "Orthodox",
            "fight_date": None, "weight_class": "Welterweight",
            "title_fight": True, "total_rounds": 12,
            "dk_odds_a": -160, "dk_odds_b": 135,
        },
    ]
    for row in demo_rows:
        _render_fight_card(row)


fight_card_page()
