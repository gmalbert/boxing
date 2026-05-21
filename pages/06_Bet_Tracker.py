"""
KnockOutIQ — Bet Tracker & CLV Logger Page
Log your bets, track closing line value, and measure long-run edge.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.db import BetLog, Fight, Fighter, get_session
from utils.odds_utils import (
    american_to_implied_prob,
    clv,
    fmt_american,
    kelly_fraction,
)
from utils.page_utils import sidebar_header


# ─── Data Loaders ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def load_bet_log() -> pd.DataFrame:
    session = get_session()
    try:
        bets = session.query(BetLog).order_by(BetLog.placed_at.desc()).all()
        if not bets:
            return pd.DataFrame()
        rows = []
        for b in bets:
            fight = session.get(Fight, b.fight_id) if b.fight_id else None
            rows.append({
                "id": b.id,
                "Fight": fight.event_name or f"Fight #{b.fight_id}" if fight else "N/A",
                "Fighter": b.fighter_name,
                "Book": b.bookmaker,
                "Odds Obtained": b.american_odds_obtained,
                "Stake (units)": b.stake_units,
                "Model Prob": b.model_prob_at_time,
                "Closing Odds": b.closing_odds,
                "CLV": b.clv,
                "Result": b.result,
                "Date": b.placed_at.date() if b.placed_at else None,
                "Notes": b.notes,
            })
        return pd.DataFrame(rows)
    finally:
        session.close()


def save_bet(bet_data: dict) -> None:
    session = get_session()
    try:
        bet = BetLog(
            fighter_name=bet_data["fighter_name"],
            bookmaker=bet_data["bookmaker"],
            american_odds_obtained=bet_data["odds_obtained"],
            stake_units=bet_data["stake"],
            model_prob_at_time=bet_data["model_prob"],
            closing_odds=bet_data.get("closing_odds"),
            result=bet_data.get("result", "pending"),
            notes=bet_data.get("notes", ""),
        )
        bet.clv = clv(bet_data["odds_obtained"], bet_data["closing_odds"]) if bet_data.get("closing_odds") else None
        session.add(bet)
        session.commit()
    finally:
        session.close()


def update_bet_result(bet_id: int, result: str, closing_odds: int | None) -> None:
    session = get_session()
    try:
        bet = session.get(BetLog, bet_id)
        if bet:
            bet.result = result
            if closing_odds:
                bet.closing_odds = closing_odds
                bet.clv = clv(bet.american_odds_obtained, closing_odds)
            session.commit()
    finally:
        session.close()


# ─── Charts ───────────────────────────────────────────────────────────────────

def _cumulative_clv_chart(df: pd.DataFrame) -> go.Figure:
    clv_col = df["CLV"].fillna(0)
    cum_clv = clv_col.cumsum()
    fig = go.Figure(go.Scatter(
        x=list(range(1, len(cum_clv) + 1)), y=cum_clv.tolist(),
        mode="lines+markers", fill="tozeroy",
        fillcolor="rgba(249,115,22,0.15)",
        line=dict(color="#f97316", width=2),
    ))
    fig.add_hline(y=0, line=dict(color="#6b7280", dash="dash"))
    fig.update_layout(
        title="Cumulative Closing Line Value",
        xaxis_title="Bet #", yaxis_title="Cumulative CLV",
        height=300, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.3)",
    )
    return fig


def _pnl_chart(df: pd.DataFrame) -> go.Figure:
    if "Result" not in df.columns or df.empty:
        return go.Figure()
    completed = df[df["Result"].isin(["win", "loss", "push"])].copy()
    if completed.empty:
        return go.Figure().add_annotation(text="No completed bets yet", showarrow=False)

    def pnl(row):
        odds = row["Odds Obtained"]
        stake = row.get("Stake (units)", 1)
        if row["Result"] == "win":
            if odds > 0:
                return stake * (odds / 100)
            return stake * (100 / abs(odds))
        elif row["Result"] == "loss":
            return -stake
        return 0

    completed["P&L"] = completed.apply(pnl, axis=1)
    completed["Cum P&L"] = completed["P&L"].cumsum()

    fig = go.Figure(go.Scatter(
        x=list(range(1, len(completed) + 1)), y=completed["Cum P&L"].tolist(),
        mode="lines+markers", fill="tozeroy",
        fillcolor="rgba(34,197,94,0.15)",
        line=dict(color="#22c55e", width=2),
    ))
    fig.add_hline(y=0, line=dict(color="#6b7280", dash="dash"))
    fig.update_layout(
        title="Cumulative P&L (units)",
        xaxis_title="Bet #", yaxis_title="Units",
        height=300, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.3)",
    )
    return fig


# ─── Page ─────────────────────────────────────────────────────────────────────

def bet_tracker_page():
    sidebar_header()
    st.title("💰 Bet Tracker & CLV Logger")
    st.caption("Log your bets · Track closing line value · Measure long-run edge")

    tab_log, tab_add, tab_update, tab_kelly = st.tabs([
        "Bet Log", "Log New Bet", "Update Result", "Kelly Calculator"
    ])

    with tab_log:
        _tab_bet_log()

    with tab_add:
        _tab_add_bet()

    with tab_update:
        _tab_update_bet()

    with tab_kelly:
        _tab_kelly()


def _tab_bet_log():
    st.subheader("Your Bet History")
    df = load_bet_log()

    if df.empty:
        st.info(
            "No bets logged yet. Use the **Log New Bet** tab to start tracking.",
            icon="ℹ️",
        )
        _demo_log()
        return

    # Summary metrics
    completed = df[df["Result"].isin(["win", "loss", "push"])]
    total_bets = len(df)
    wins = (completed["Result"] == "win").sum()
    losses = (completed["Result"] == "loss").sum()
    win_rate = wins / len(completed) if len(completed) else 0
    clv_vals = df["CLV"].dropna()
    avg_clv = clv_vals.mean() if len(clv_vals) else 0

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Bets", total_bets)
    m2.metric("Win Rate", f"{win_rate:.1%}")
    m3.metric("Wins / Losses", f"{wins} / {losses}")
    m4.metric("Avg CLV", f"{avg_clv:+.1%}" if len(clv_vals) else "N/A")
    m5.metric("CLV Signal", "✅ +EV" if avg_clv > 0 else "⚠️ Review")

    # Charts
    ch1, ch2 = st.columns(2)
    with ch1:
        st.plotly_chart(_cumulative_clv_chart(df), width="stretch")
    with ch2:
        st.plotly_chart(_pnl_chart(df), width="stretch")

    # Table
    display_cols = ["Fight", "Fighter", "Book", "Odds Obtained", "Stake (units)",
                    "Model Prob", "Closing Odds", "CLV", "Result", "Date"]
    show_df = df[[c for c in display_cols if c in df.columns]].copy()

    def fmt_clv(val):
        if pd.isna(val):
            return ""
        return f"{val:+.1%}"

    def fmt_prob(val):
        if pd.isna(val):
            return ""
        return f"{val:.1%}"

    show_df["CLV"] = show_df["CLV"].apply(fmt_clv)
    show_df["Model Prob"] = show_df["Model Prob"].apply(fmt_prob)

    def highlight_result(val):
        if val == "win":
            return "color: #22c55e; font-weight: bold"
        elif val == "loss":
            return "color: #ef4444"
        return ""

    styled = show_df.style.map(highlight_result, subset=["Result"])
    st.dataframe(styled, width="stretch", hide_index=True)


def _demo_log():
    st.markdown("#### Demo Log Preview")
    demo_data = [
        {"Fight": "Crawford vs. Spence", "Fighter": "T. Crawford", "Book": "DraftKings",
         "Odds": "-155", "Stake": "2u", "Model Prob": "67%", "Closing": "-175",
         "CLV": "+3.1%", "Result": "win"},
        {"Fight": "Canelo vs. Bivol", "Fighter": "D. Bivol", "Book": "DraftKings",
         "Odds": "+115", "Stake": "1u", "Model Prob": "46%", "Closing": "+118",
         "CLV": "+0.5%", "Result": "win"},
    ]
    st.caption("Demo data — your real bets will appear here once logged")
    st.dataframe(pd.DataFrame(demo_data), width="stretch", hide_index=True)


def _tab_add_bet():
    st.subheader("Log a New Bet")
    with st.form("add_bet_form"):
        col1, col2 = st.columns(2)
        with col1:
            fighter_name = st.text_input("Fighter Name *", placeholder="e.g. Terence Crawford")
            odds_obtained = st.number_input("Odds Obtained (American) *", value=-110, step=5)
            model_prob = st.slider("Your Model Probability (%)", 0, 100, 55) / 100
        with col2:
            bookmaker = st.selectbox("Bookmaker", ["draftkings", "fanduel", "betmgm", "other"])
            stake = st.number_input("Stake (units)", min_value=0.1, value=1.0, step=0.5)
            notes = st.text_area("Notes", placeholder="Context, reasoning…")

        closing_odds = st.number_input("Closing Odds (fill after fight)", value=0, step=5)
        result = st.selectbox("Result", ["pending", "win", "loss", "push"])

        submitted = st.form_submit_button("Log Bet", type="primary")

    if submitted:
        if not fighter_name:
            st.error("Fighter name is required.")
        else:
            save_bet({
                "fighter_name": fighter_name,
                "bookmaker": bookmaker,
                "odds_obtained": odds_obtained,
                "stake": stake,
                "model_prob": model_prob,
                "closing_odds": closing_odds if closing_odds != 0 else None,
                "result": result,
                "notes": notes,
            })
            load_bet_log.clear()
            st.success(f"✅ Bet on {fighter_name} logged!")
            st.rerun()


def _tab_update_bet():
    st.subheader("Update Bet Result")
    df = load_bet_log()
    if df.empty:
        st.info("No bets to update.", icon="ℹ️")
        return

    pending = df[df["Result"] == "pending"]
    if pending.empty:
        st.success("All bets have results recorded.")
        return

    bet_options = {
        row["id"]: f"{row['Fighter']} @ {fmt_american(row['Odds Obtained'])} — {row['Date']}"
        for _, row in pending.iterrows()
    }

    with st.form("update_bet_form"):
        selected_id = st.selectbox(
            "Select Bet to Update",
            list(bet_options.keys()),
            format_func=lambda i: bet_options[i],
        )
        new_result = st.selectbox("Result", ["win", "loss", "push"])
        new_closing = st.number_input("Closing Odds", value=0, step=5)
        update_submitted = st.form_submit_button("Update", type="primary")

    if update_submitted:
        update_bet_result(
            selected_id, new_result,
            new_closing if new_closing != 0 else None,
        )
        load_bet_log.clear()
        st.success("Bet updated!")
        st.rerun()


def _tab_kelly():
    st.subheader("Kelly Criterion Stake Calculator")
    st.markdown(
        "Use fractional Kelly to size your bets optimally. "
        "**Quarter Kelly (25%) is recommended** to reduce variance."
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        model_pct = st.slider("Model Win Probability", 0, 100, 60) / 100
    with col2:
        dk_odds = st.number_input("DraftKings Odds", value=-110, step=5)
    with col3:
        bankroll = st.number_input("Bankroll ($)", value=1000, step=100)

    fraction = st.radio("Kelly Fraction", [0.25, 0.5, 1.0], index=0,
                        format_func=lambda x: f"{x:.0%} Kelly")

    kelly = kelly_fraction(model_pct, dk_odds, fraction=fraction)
    stake_dollars = kelly * bankroll
    from utils.odds_utils import american_to_decimal
    dec_odds = american_to_decimal(dk_odds)
    expected_profit = stake_dollars * (model_pct * (dec_odds - 1) - (1 - model_pct))

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Kelly %", f"{kelly:.1%}")
    k2.metric("Recommended Stake", f"${stake_dollars:.2f}")
    k3.metric("Expected Profit", f"${expected_profit:.2f}")
    k4.metric("Edge", f"{model_pct - american_to_implied_prob(dk_odds):+.1%}")

    if kelly == 0:
        st.warning("Kelly says: **No Bet** — model probability is not high enough vs. these odds.")


bet_tracker_page()
