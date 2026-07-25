"""
KnockOutIQ — Odds Tracker / Line Movement Page
DraftKings vs. Pinnacle live comparison and historical line movement.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.db import Fight, Fighter, OddsSnapshot, get_session
from utils.odds_utils import (
    american_to_implied_prob,
    fmt_american,
    no_vig_prob_from_american,
    edge_label,
)
from utils.page_utils import sidebar_header


# ─── Data Loaders ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def load_odds_data() -> list[dict]:
    """Latest odds snapshot grouped by fight/fighter/bookmaker."""
    session = get_session()
    try:
        snaps = (
            session.query(OddsSnapshot)
            .order_by(OddsSnapshot.snapshot_time.desc())
            .all()
        )
        grouped: dict[str, dict] = {}
        for s in snaps:
            key = s.external_fight_id or str(s.fight_id)
            if key not in grouped:
                grouped[key] = {"event_id": key, "bookmakers": {}}
            if s.bookmaker not in grouped[key]["bookmakers"]:
                grouped[key]["bookmakers"][s.bookmaker] = {}
            if s.fighter_name not in grouped[key]["bookmakers"][s.bookmaker]:
                grouped[key]["bookmakers"][s.bookmaker][s.fighter_name] = s.american_odds

        rows = []
        for key, data in grouped.items():
            bk = data["bookmakers"]
            fighters = list(set(
                name
                for bk_odds in bk.values()
                for name in bk_odds.keys()
            ))
            if len(fighters) < 2:
                continue
            fa_name, fb_name = fighters[0], fighters[1]
            rows.append({
                "event_id": key,
                "fighter_a": fa_name,
                "fighter_b": fb_name,
                "dk_a": bk.get("draftkings", {}).get(fa_name),
                "dk_b": bk.get("draftkings", {}).get(fb_name),
                "pin_a": bk.get("pinnacle", {}).get(fa_name),
                "pin_b": bk.get("pinnacle", {}).get(fb_name),
                "fd_a": bk.get("fanduel", {}).get(fa_name),
                "fd_b": bk.get("fanduel", {}).get(fb_name),
            })
        return rows
    finally:
        session.close()


@st.cache_data(ttl=60, show_spinner=False)
def load_odds_history(fight_id: int, fighter_name: str, bookmaker: str) -> list[dict]:
    session = get_session()
    try:
        snaps = (
            session.query(OddsSnapshot)
            .filter(
                OddsSnapshot.fight_id == fight_id,
                OddsSnapshot.fighter_name == fighter_name,
                OddsSnapshot.bookmaker == bookmaker,
            )
            .order_by(OddsSnapshot.snapshot_time)
            .all()
        )
        return [{"time": s.snapshot_time, "odds": s.american_odds} for s in snaps]
    finally:
        session.close()


# ─── Charts ───────────────────────────────────────────────────────────────────

def _line_movement_chart(dk_history: list[dict], pin_history: list[dict], fighter_name: str) -> go.Figure:
    fig = go.Figure()
    if dk_history:
        times_dk = [h["time"] for h in dk_history]
        odds_dk = [h["odds"] for h in dk_history]
        fig.add_trace(go.Scatter(
            x=times_dk, y=odds_dk, mode="lines+markers",
            name="DraftKings", line=dict(color="#22c55e", width=2),
            marker=dict(size=6),
        ))
    if pin_history:
        times_pin = [h["time"] for h in pin_history]
        odds_pin = [h["odds"] for h in pin_history]
        fig.add_trace(go.Scatter(
            x=times_pin, y=odds_pin, mode="lines+markers",
            name="Pinnacle", line=dict(color="#a855f7", width=2, dash="dot"),
            marker=dict(size=6),
        ))
    fig.update_layout(
        title=f"{fighter_name} — Line Movement",
        xaxis_title="Time", yaxis_title="American Odds",
        height=350, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.3)",
        legend=dict(orientation="h"),
    )
    return fig


def _multi_book_bar(row: dict) -> go.Figure:
    """Bar chart comparing a fighter's odds across bookmakers."""
    books = ["draftkings", "fanduel", "pinnacle"]
    labels = ["DraftKings", "FanDuel", "Pinnacle"]
    odds_a = [row.get(f"{b[:2]}_a") or row.get(f"dk_a") for b in ["dk", "fd", "pin"]]
    odds_b = [row.get(f"{b[:2]}_b") or row.get(f"dk_b") for b in ["dk", "fd", "pin"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(name=row["fighter_a"], x=labels, y=odds_a, marker_color="#f97316"))
    fig.add_trace(go.Bar(name=row["fighter_b"], x=labels, y=odds_b, marker_color="#3b82f6"))
    fig.update_layout(
        barmode="group", title="Current Odds by Bookmaker",
        yaxis_title="American Odds", height=300,
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h"),
    )
    return fig


# ─── Demo Data ────────────────────────────────────────────────────────────────

def _demo_line_movement() -> go.Figure:
    now = datetime.now(datetime.UTC)
    times = [now - timedelta(hours=h) for h in range(48, 0, -6)]
    dk_odds = [-130, -128, -125, -125, -122, -120, -118, -115]
    pin_odds = [-140, -138, -135, -132, -130, -128, -125, -122]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=times, y=dk_odds, mode="lines+markers",
        name="DraftKings", line=dict(color="#22c55e", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=times, y=pin_odds, mode="lines+markers",
        name="Pinnacle (sharp)", line=dict(color="#a855f7", width=2, dash="dot"),
    ))
    fig.add_annotation(
        x=times[5], y=dk_odds[5],
        text="Sharp money → line moved",
        showarrow=True, arrowhead=1, bgcolor="#1e293b", font=dict(color="white"),
    )
    fig.update_layout(
        title="Demo: Canelo vs. Bivol — Line Movement (48h)",
        xaxis_title="Time", yaxis_title="American Odds",
        height=400, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.3)",
    )
    return fig


# ─── Page ─────────────────────────────────────────────────────────────────────

def odds_tracker_page():
    sidebar_header()
    st.title("📈 Odds Tracker")
    st.caption("DraftKings vs. Pinnacle · Line movement · Sharp money signals")

    # Auto-refresh toggle
    auto_refresh = st.sidebar.checkbox("Auto-refresh every 5 min", value=False)
    if auto_refresh:
        st.sidebar.caption("Live refresh enabled")

    tab_live, tab_movement, tab_calc = st.tabs(["Live Odds Board", "Line Movement", "Odds Calculator"])

    with tab_live:
        _tab_live_odds()

    with tab_movement:
        _tab_line_movement()

    with tab_calc:
        _tab_odds_calculator()


def _tab_live_odds():
    st.subheader("Current Odds Board")

    if st.button("🔄 Refresh", key="refresh_live"):
        load_odds_data.clear()
        st.rerun()

    rows = load_odds_data()

    if not rows:
        st.info("No odds data loaded yet. Run the daily update to fetch live odds.", icon="ℹ️")
        _demo_odds_board()
        return

    df_rows = []
    for row in rows:
        dk_a = row["dk_a"]
        dk_b = row["dk_b"]
        pin_a = row["pin_a"]

        pin_edge = ""
        if dk_a and pin_a:
            from utils.odds_utils import american_to_implied_prob
            pin_implied = american_to_implied_prob(pin_a)
            dk_implied = american_to_implied_prob(dk_a)
            edge = pin_implied - dk_implied
            lbl, _ = edge_label(edge)
            pin_edge = f"{edge:+.1%} {lbl[:2]}"

        df_rows.append({
            "Fighter A": row["fighter_a"],
            "DK A": fmt_american(dk_a),
            "FD A": fmt_american(row.get("fd_a")),
            "Pinnacle A": fmt_american(pin_a),
            "vs.": "—",
            "Fighter B": row["fighter_b"],
            "DK B": fmt_american(dk_b),
            "FD B": fmt_american(row.get("fd_b")),
            "Pinnacle B": fmt_american(row.get("pin_b")),
            "Pin Edge": pin_edge,
        })

    df = pd.DataFrame(df_rows)
    st.dataframe(df, width="stretch", hide_index=True)


def _demo_odds_board():
    demo = [
        {"Fighter A": "Canelo Álvarez", "DK A": "-130", "FD A": "-128", "Pinnacle A": "-140",
         "vs.": "—", "Fighter B": "Dmitry Bivol", "DK B": "+110", "FD B": "+108", "Pinnacle B": "+118",
         "Pin Edge": "+3.5% 🟡"},
        {"Fighter A": "Terence Crawford", "DK A": "-160", "FD A": "-155", "Pinnacle A": "-175",
         "vs.": "—", "Fighter B": "Errol Spence Jr.", "DK B": "+135", "FD B": "+130", "Pinnacle B": "+148",
         "Pin Edge": "+4.2% 🟢"},
    ]
    st.caption("Demo data — connect APIs to see live odds")
    st.dataframe(pd.DataFrame(demo), width="stretch", hide_index=True)


def _tab_line_movement():
    st.subheader("Line Movement History")
    rows = load_odds_data()

    if not rows:
        st.info("No historical odds data. Showing demo movement chart.", icon="ℹ️")
        st.plotly_chart(_demo_line_movement(), width="stretch")
        return

    fight_labels = [f"{r['fighter_a']} vs. {r['fighter_b']}" for r in rows]
    selected_idx = st.selectbox("Select Fight", range(len(fight_labels)),
                                format_func=lambda i: fight_labels[i])
    selected_row = rows[selected_idx]
    fighter_choice = st.radio("Fighter", [selected_row["fighter_a"], selected_row["fighter_b"]])

    event_id = selected_row["event_id"]
    try:
        fight_id = int(event_id)
    except ValueError:
        fight_id = 0

    dk_hist = load_odds_history(fight_id, fighter_choice, "draftkings")
    pin_hist = load_odds_history(fight_id, fighter_choice, "pinnacle")

    if not dk_hist and not pin_hist:
        st.info("Not enough history to plot movement yet.")
        st.plotly_chart(_demo_line_movement(), width="stretch")
    else:
        st.plotly_chart(_line_movement_chart(dk_hist, pin_hist, fighter_choice), width="stretch")
        st.plotly_chart(_multi_book_bar(selected_row), width="stretch")


def _tab_odds_calculator():
    st.subheader("Odds Converter & Edge Calculator")
    st.markdown("Convert between odds formats and calculate implied probabilities.")

    col1, col2 = st.columns(2)
    with col1:
        american = st.number_input("American Odds", value=-110, step=5)
        imp = american_to_implied_prob(american)
        st.metric("Implied Probability", f"{imp:.1%}")
        st.metric("Decimal Odds", f"{1 / imp:.3f}")

    with col2:
        st.markdown("#### Edge Calculator")
        model_pct = st.slider("Your Model's Win Probability", 0, 100, 55) / 100
        dk_odds = st.number_input("DraftKings Odds", value=-110, step=5, key="calc_dk")
        edge = model_pct - american_to_implied_prob(dk_odds)
        lbl, color = edge_label(edge)
        st.metric("Edge", f"{edge:+.1%}")
        st.markdown(f"**Signal:** {lbl}")

    st.markdown("---")
    st.markdown("#### Two-Way No-Vig Calculator")
    c1, c2 = st.columns(2)
    with c1:
        odds_x = st.number_input("Fighter A American odds", value=-160, step=5, key="nv1")
    with c2:
        odds_y = st.number_input("Fighter B American odds", value=140, step=5, key="nv2")

    fa_p, fb_p = no_vig_prob_from_american(odds_x, odds_y)
    nv1, nv2 = st.columns(2)
    nv1.metric("Fighter A No-Vig Prob", f"{fa_p:.1%}")
    nv2.metric("Fighter B No-Vig Prob", f"{fb_p:.1%}")
    st.caption(f"Vig (overround): {(american_to_implied_prob(odds_x) + american_to_implied_prob(odds_y) - 1):.1%}")


odds_tracker_page()
