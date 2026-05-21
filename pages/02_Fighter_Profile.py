"""
KnockOutIQ — Fighter Profile Page
Per-fighter deep dive: career record, stats, Elo history, style.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import or_

from data.db import EloHistory, Fight, Fighter, get_session
from utils.odds_utils import fmt_american
from utils.page_utils import sidebar_header


# ─── Data Loaders ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def load_fighter_names() -> list[str]:
    session = get_session()
    try:
        fighters = session.query(Fighter.name).order_by(Fighter.name).all()
        return [f[0] for f in fighters]
    finally:
        session.close()


@st.cache_data(ttl=300, show_spinner=False)
def load_fighter_detail(fighter_name: str) -> dict | None:
    session = get_session()
    try:
        fighter = (
            session.query(Fighter)
            .filter(Fighter.name.ilike(f"%{fighter_name}%"))
            .first()
        )
        if not fighter:
            return None

        fights = (
            session.query(Fight)
            .filter(
                or_(Fight.fighter_a_id == fighter.id, Fight.fighter_b_id == fighter.id),
                Fight.is_upcoming == False,
            )
            .order_by(Fight.fight_date.desc())
            .all()
        )

        elo_hist = (
            session.query(EloHistory)
            .filter(EloHistory.fighter_id == fighter.id)
            .order_by(EloHistory.recorded_at)
            .all()
        )

        fight_list = []
        for f in fights:
            opp_id = f.fighter_b_id if f.fighter_a_id == fighter.id else f.fighter_a_id
            opp = session.get(Fighter, opp_id)
            side = "A" if f.fighter_a_id == fighter.id else "B"
            won = f.result == side
            drew = f.result in ("draw", "NC")
            fight_list.append({
                "date": f.fight_date,
                "opponent": opp.name if opp else "Unknown",
                "result": "W" if won else ("D" if drew else "L"),
                "method": f.method or "N/A",
                "rounds": f.round_ended or f.total_rounds or "N/A",
                "title_fight": f.title_fight,
                "weight_class": f.weight_class or "N/A",
            })

        age = None
        if fighter.birth_date:
            today = date.today()
            age = today.year - fighter.birth_date.year - (
                (today.month, today.day) < (fighter.birth_date.month, fighter.birth_date.day)
            )

        return {
            "id": fighter.id,
            "name": fighter.name,
            "record": f"{fighter.wins}-{fighter.losses}-{fighter.draws}",
            "wins": fighter.wins or 0,
            "losses": fighter.losses or 0,
            "draws": fighter.draws or 0,
            "ko_wins": fighter.ko_wins or 0,
            "tko_wins": fighter.tko_wins or 0,
            "dec_wins": max(0, (fighter.wins or 0) - (fighter.ko_wins or 0) - (fighter.tko_wins or 0)),
            "stance": fighter.stance or "Unknown",
            "height_cm": fighter.height_cm,
            "reach_cm": fighter.reach_cm,
            "nationality": fighter.nationality or "Unknown",
            "weight_class": fighter.weight_class or "Unknown",
            "elo": fighter.elo_rating or 1500,
            "age": age,
            "style_tag": fighter.style_tag,
            "fights": fight_list,
            "elo_history": [(h.recorded_at, h.elo_after) for h in elo_hist],
        }
    finally:
        session.close()


# ─── Charts ───────────────────────────────────────────────────────────────────

def _elo_chart(history: list[tuple]) -> go.Figure:
    if not history:
        return go.Figure().add_annotation(text="No Elo history", showarrow=False)
    dates, ratings = zip(*history)
    fig = go.Figure(go.Scatter(
        x=dates, y=ratings, mode="lines+markers",
        line=dict(color="#f97316", width=2),
        marker=dict(size=5),
        fill="tozeroy", fillcolor="rgba(249,115,22,0.1)",
    ))
    fig.update_layout(
        title="Elo Rating Over Career",
        xaxis_title="Date", yaxis_title="Elo",
        height=300, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.3)",
    )
    return fig


def _win_breakdown_chart(detail: dict) -> go.Figure:
    labels = ["KO/TKO", "Decision", "Other"]
    values = [
        detail["ko_wins"] + detail["tko_wins"],
        detail["dec_wins"],
        max(0, detail["wins"] - detail["ko_wins"] - detail["tko_wins"] - detail["dec_wins"]),
    ]
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.4, marker_colors=["#ef4444", "#3b82f6", "#6b7280"],
    ))
    fig.update_layout(
        title="Win Breakdown", height=280,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h"),
    )
    return fig


# ─── Demo Data ────────────────────────────────────────────────────────────────

_DEMO_FIGHTERS = {
    "Canelo Álvarez": {
        "id": 0, "name": "Canelo Álvarez", "record": "60-2-2",
        "wins": 60, "losses": 2, "draws": 2,
        "ko_wins": 29, "tko_wins": 10, "dec_wins": 21,
        "stance": "Orthodox", "height_cm": 173, "reach_cm": 179,
        "nationality": "Mexico", "weight_class": "Super Middleweight",
        "elo": 1830, "age": 35, "style_tag": "Boxer-Puncher",
        "fights": [
            {"date": None, "opponent": "Dmitry Bivol", "result": "L", "method": "UD", "rounds": 12, "title_fight": True, "weight_class": "Light Heavyweight"},
            {"date": None, "opponent": "Gennadiy Golovkin", "result": "W", "method": "UD", "rounds": 12, "title_fight": True, "weight_class": "Middleweight"},
        ],
        "elo_history": [],
    },
    "Terence Crawford": {
        "id": 1, "name": "Terence Crawford", "record": "40-0-0",
        "wins": 40, "losses": 0, "draws": 0,
        "ko_wins": 20, "tko_wins": 9, "dec_wins": 11,
        "stance": "Southpaw", "height_cm": 175, "reach_cm": 179,
        "nationality": "USA", "weight_class": "Welterweight",
        "elo": 1920, "age": 37, "style_tag": "Switch-hitter",
        "fights": [],
        "elo_history": [],
    },
}


# ─── Page ─────────────────────────────────────────────────────────────────────

def fighter_profile_page():
    sidebar_header()
    st.title("🥊 Fighter Profile")
    st.caption("Career record · Physical stats · Elo rating · Style analysis")

    names = load_fighter_names()
    demo_mode = len(names) == 0

    if demo_mode:
        st.info("Database not yet populated. Showing demo data.", icon="ℹ️")
        names = list(_DEMO_FIGHTERS.keys())

    # Search
    search = st.text_input("Search fighter name", placeholder="e.g. Canelo, Crawford…")
    filtered_names = [n for n in names if search.lower() in n.lower()] if search else names

    if not filtered_names:
        st.warning(f"No fighters found matching '{search}'")
        return

    selected = st.selectbox("Select Fighter", filtered_names)
    if not selected:
        return

    with st.spinner("Loading profile…"):
        if demo_mode:
            detail = _DEMO_FIGHTERS.get(selected)
        else:
            detail = load_fighter_detail(selected)

    if not detail:
        st.error("Fighter not found.")
        return

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(f"## {detail['name']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Record", detail["record"])
    c2.metric("Elo Rating", f"{detail['elo']:.0f}")
    c3.metric("Weight Class", detail["weight_class"])
    c4.metric("Style", detail["style_tag"] or "N/A")

    st.markdown("---")

    # ── Physical Stats ─────────────────────────────────────────────────────
    with st.expander("Physical Stats", expanded=True):
        p1, p2, p3, p4, p5 = st.columns(5)
        p1.metric("Stance", detail["stance"])
        p2.metric("Height", f"{detail['height_cm']} cm" if detail["height_cm"] else "N/A")
        p3.metric("Reach", f"{detail['reach_cm']} cm" if detail["reach_cm"] else "N/A")
        p4.metric("Age", detail["age"] or "N/A")
        p5.metric("Nationality", detail["nationality"])

    # ── Win Breakdown + Elo Chart ─────────────────────────────────────────
    ch1, ch2 = st.columns(2)
    with ch1:
        st.plotly_chart(_win_breakdown_chart(detail), width="stretch")
    with ch2:
        st.plotly_chart(_elo_chart(detail["elo_history"]), width="stretch")

    # ── Record Details ────────────────────────────────────────────────────
    st.markdown("### Win Statistics")
    w1, w2, w3, w4 = st.columns(4)
    total_wins = detail["wins"]
    w1.metric("KO Wins", detail["ko_wins"])
    w2.metric("TKO Wins", detail["tko_wins"])
    w3.metric("Decision Wins", detail["dec_wins"])
    w4.metric("KO/TKO Rate", f"{(detail['ko_wins']+detail['tko_wins'])/total_wins:.0%}" if total_wins else "N/A")

    # ── Recent Fights Table ────────────────────────────────────────────────
    st.markdown("### Fight History")
    fights = detail["fights"]
    if not fights:
        st.info("No fight records available.")
    else:
        df = pd.DataFrame(fights)
        df = df.rename(columns={
            "date": "Date", "opponent": "Opponent", "result": "W/L/D",
            "method": "Method", "rounds": "Rounds",
            "title_fight": "Title 🏆", "weight_class": "Weight Class",
        })

        def style_result(val):
            if val == "W":
                return "color: #22c55e; font-weight: bold"
            elif val == "L":
                return "color: #ef4444; font-weight: bold"
            return "color: #facc15; font-weight: bold"

        styled = df.style.map(style_result, subset=["W/L/D"])
        st.dataframe(styled, width="stretch", hide_index=True)


fighter_profile_page()
