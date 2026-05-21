"""
KnockOutIQ — Model Dashboard Page
All upcoming fights ranked by edge. Model prob vs. DK implied prob.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data.db import Fight, Fighter, ModelPrediction, OddsSnapshot, get_session
from utils.odds_utils import (
    american_to_implied_prob,
    calculate_edge,
    edge_label,
    fmt_american,
    no_vig_prob_from_american,
)
import models.logistic_model as lm
import models.xgboost_model as xgb
from sqlalchemy import or_
from utils.page_utils import sidebar_header


# ─── Data Loaders ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def load_model_signals() -> list[dict]:
    """Build model predictions for all upcoming fights and rank by edge."""
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

            # Build features
            def win_pct(f):
                t = (f.wins or 0) + (f.losses or 0)
                return (f.wins or 0) / t if t else 0.5

            def ko_pct(f):
                w = f.wins or 1
                k = (f.ko_wins or 0) + (f.tko_wins or 0)
                return k / w

            features = {
                "reach_diff": (fa.reach_cm or 0) - (fb.reach_cm or 0),
                "height_diff": (fa.height_cm or 0) - (fb.height_cm or 0),
                "age_diff": 0,
                "win_pct_diff": win_pct(fa) - win_pct(fb),
                "ko_pct_diff": ko_pct(fa) - ko_pct(fb),
                "elo_diff": (fa.elo_rating or 1500) - (fb.elo_rating or 1500),
                "days_since_last_fight_diff": 0,
                "opposition_quality_diff": 0,
                "is_southpaw_matchup": int(
                    (fa.stance or "Orthodox").lower() != (fb.stance or "Orthodox").lower()
                ),
            }

            prob_a = lm.predict_proba(features)
            xgb_prob_a, confidence = xgb.predict_proba(features)

            # Get DK odds
            snaps = (
                session.query(OddsSnapshot)
                .filter(OddsSnapshot.fight_id == fight.id, OddsSnapshot.bookmaker == "draftkings")
                .order_by(OddsSnapshot.snapshot_time.desc())
                .limit(4)
                .all()
            )
            dk_a = next((s.american_odds for s in snaps if s.fighter_name == fa.name), None)
            dk_b = next((s.american_odds for s in snaps if s.fighter_name == fb.name), None)

            edge_a = calculate_edge(prob_a, dk_a) if dk_a else None
            edge_b = calculate_edge(1 - prob_a, dk_b) if dk_b else None
            best_edge = max(edge_a or -1, edge_b or -1)
            best_fighter = fa.name if (edge_a or -1) >= (edge_b or -1) else fb.name

            lbl, _ = edge_label(best_edge)

            rows.append({
                "fight_date": fight.fight_date,
                "matchup": f"{fa.name} vs. {fb.name}",
                "fighter_a": fa.name,
                "fighter_b": fb.name,
                "weight_class": fight.weight_class or "N/A",
                "title_fight": fight.title_fight,
                "model_prob_a": prob_a,
                "model_prob_b": 1 - prob_a,
                "xgb_prob_a": xgb_prob_a,
                "confidence": confidence,
                "dk_a": dk_a,
                "dk_b": dk_b,
                "dk_implied_a": american_to_implied_prob(dk_a) if dk_a else None,
                "dk_implied_b": american_to_implied_prob(dk_b) if dk_b else None,
                "edge_a": edge_a,
                "edge_b": edge_b,
                "best_edge": best_edge,
                "best_fighter": best_fighter,
                "edge_label": lbl,
            })

        rows.sort(key=lambda r: r["best_edge"] or -1, reverse=True)
        return rows
    finally:
        session.close()


@st.cache_data(ttl=600, show_spinner=False)
def load_historical_accuracy() -> pd.DataFrame:
    """Load historical model predictions vs actual results."""
    session = get_session()
    try:
        preds = session.query(ModelPrediction).all()
        if not preds:
            return pd.DataFrame()
        data = []
        for p in preds:
            fight = session.get(Fight, p.fight_id) if p.fight_id else None
            if not fight or not fight.result:
                continue
            predicted_winner = "A" if (p.fighter_a_win_prob or 0.5) >= 0.5 else "B"
            correct = predicted_winner == fight.result
            data.append({
                "model_version": p.model_version,
                "predicted_prob": p.fighter_a_win_prob,
                "correct": correct,
                "fight_date": fight.fight_date,
            })
        return pd.DataFrame(data)
    finally:
        session.close()


# ─── Charts ───────────────────────────────────────────────────────────────────

def _edge_scatter(rows: list[dict]) -> go.Figure:
    if not rows:
        return go.Figure()
    fig = go.Figure()
    for row in rows:
        if row["model_prob_a"] is None or row["dk_implied_a"] is None:
            continue
        lbl, color = edge_label(row["edge_a"] or 0)
        fig.add_trace(go.Scatter(
            x=[row["dk_implied_a"]],
            y=[row["model_prob_a"]],
            mode="markers+text",
            marker=dict(size=14, color=color, line=dict(color="white", width=1)),
            text=[row["fighter_a"][:10]],
            textposition="top center",
            name=row["matchup"],
            showlegend=False,
        ))
    # Diagonal = no edge
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1], mode="lines",
        line=dict(color="#6b7280", dash="dash", width=1),
        name="No Edge Line",
    ))
    fig.update_layout(
        title="Model Probability vs. DK Implied Probability",
        xaxis_title="DK Implied Probability",
        yaxis_title="Model Probability",
        xaxis=dict(range=[0, 1]), yaxis=dict(range=[0, 1]),
        height=400, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.3)",
    )
    return fig


def _calibration_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure().add_annotation(text="No prediction history yet", showarrow=False)
    bins = np.arange(0, 1.1, 0.1)
    df["bin"] = pd.cut(df["predicted_prob"], bins=bins)
    cal = df.groupby("bin")["correct"].mean().reset_index()
    cal["bin_mid"] = [b.mid for b in cal["bin"]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1], mode="lines",
        line=dict(color="#6b7280", dash="dash"), name="Perfect Calibration",
    ))
    fig.add_trace(go.Scatter(
        x=cal["bin_mid"].tolist(), y=cal["correct"].tolist(),
        mode="lines+markers", name="Model",
        line=dict(color="#f97316", width=2), marker=dict(size=8),
    ))
    fig.update_layout(
        title="Model Calibration",
        xaxis_title="Predicted Probability", yaxis_title="Actual Win Rate",
        height=300, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.3)",
    )
    return fig


# ─── Demo Data ────────────────────────────────────────────────────────────────

def _demo_signals() -> list[dict]:
    return [
        {"matchup": "Canelo vs. Bivol", "fighter_a": "Canelo Álvarez", "fighter_b": "Dmitry Bivol",
         "weight_class": "Light Heavyweight", "title_fight": True,
         "model_prob_a": 0.54, "model_prob_b": 0.46,
         "xgb_prob_a": 0.52, "confidence": 0.08,
         "dk_a": -130, "dk_b": 110,
         "dk_implied_a": 0.565, "dk_implied_b": 0.476,
         "edge_a": 0.054 - 0.565, "edge_b": 0.46 - 0.476,
         "best_edge": 0.046 - 0.565, "best_fighter": "Dmitry Bivol",
         "edge_label": "🟢 Strong Edge", "fight_date": None},
        {"matchup": "Crawford vs. Spence", "fighter_a": "Terence Crawford", "fighter_b": "Errol Spence Jr.",
         "weight_class": "Welterweight", "title_fight": True,
         "model_prob_a": 0.67, "model_prob_b": 0.33,
         "xgb_prob_a": 0.65, "confidence": 0.30,
         "dk_a": -160, "dk_b": 135,
         "dk_implied_a": 0.615, "dk_implied_b": 0.426,
         "edge_a": 0.067 - 0.615, "edge_b": 0.033 - 0.426,
         "best_edge": 0.055, "best_fighter": "Terence Crawford",
         "edge_label": "🟢 Strong Edge", "fight_date": None},
    ]


# ─── Page ─────────────────────────────────────────────────────────────────────

def model_dashboard_page():
    sidebar_header()
    st.title("🤖 Model Dashboard")
    st.caption("Upcoming fights ranked by edge · Model vs. DK implied probability · Accuracy metrics")

    signals = load_model_signals()
    demo_mode = len(signals) == 0
    if demo_mode:
        st.info("No upcoming fights in database. Showing demo signals.", icon="ℹ️")
        signals = _demo_signals()

    tab_signals, tab_chart, tab_accuracy = st.tabs(["Edge Signals", "Probability Chart", "Model Accuracy"])

    with tab_signals:
        _tab_signals(signals)

    with tab_chart:
        st.plotly_chart(_edge_scatter(signals), width="stretch")
        st.caption("Points **above** the diagonal = model is more confident than DK's price. Potential +EV.")

    with tab_accuracy:
        _tab_accuracy()


def _tab_signals(signals: list[dict]):
    # Filters
    col1, col2 = st.columns(2)
    with col1:
        min_edge = st.slider("Minimum Edge %", 0, 15, 0) / 100
    with col2:
        min_conf = st.slider("Minimum XGB Confidence", 0, 100, 0) / 100

    filtered = [s for s in signals
                if (s["best_edge"] or 0) >= min_edge
                and (s["confidence"] or 0) >= min_conf]

    if not filtered:
        st.warning("No signals meet the filter criteria.")
        return

    st.markdown(f"**{len(filtered)} signal(s)** ranked by edge")

    for sig in filtered:
        _render_signal_card(sig)


def _render_signal_card(sig: dict):
    lbl, color = edge_label(sig["best_edge"] or 0)
    with st.container(border=True):
        h1, h2, h3 = st.columns([3, 1, 3])
        with h1:
            st.markdown(f"**{sig['fighter_a']}**")
            st.caption(f"Model: {sig['model_prob_a']:.1%} | DK Implied: {american_to_implied_prob(sig['dk_a']):.1%}" if sig['dk_a'] else f"Model: {sig['model_prob_a']:.1%}")
        with h2:
            st.markdown(f"<div style='text-align:center'>{sig['weight_class']}<br>{'🏆' if sig['title_fight'] else ''}</div>",
                        unsafe_allow_html=True)
        with h3:
            st.markdown(f"**{sig['fighter_b']}**")
            st.caption(f"Model: {sig['model_prob_b']:.1%} | DK Implied: {american_to_implied_prob(sig['dk_b']):.1%}" if sig['dk_b'] else f"Model: {sig['model_prob_b']:.1%}")

        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Best Edge", f"{sig['best_edge']:+.1%}" if sig['best_edge'] else "N/A")
        e2.metric("Best Pick", sig["best_fighter"])
        e3.metric("XGB Prob", f"{sig['xgb_prob_a']:.1%}")
        e4.metric("Confidence", f"{sig['confidence']:.0%}")
        st.markdown(f"**Signal:** {lbl}")


def _tab_accuracy():
    df = load_historical_accuracy()
    if df.empty:
        st.info("No historical predictions recorded yet. Accuracy metrics will appear after the model has made predictions.", icon="ℹ️")
        _demo_accuracy()
        return

    total = len(df)
    correct = df["correct"].sum()
    acc = correct / total if total else 0

    m1, m2, m3 = st.columns(3)
    m1.metric("Predictions Made", total)
    m2.metric("Accuracy", f"{acc:.1%}")
    m3.metric("Win Rate vs. Random", f"{acc - 0.5:+.1%}")

    st.plotly_chart(_calibration_chart(df), width="stretch")

    by_version = df.groupby("model_version")["correct"].agg(["mean", "count"]).reset_index()
    by_version.columns = ["Model Version", "Accuracy", "# Predictions"]
    by_version["Accuracy"] = by_version["Accuracy"].map("{:.1%}".format)
    st.dataframe(by_version, width="stretch", hide_index=True)


def _demo_accuracy():
    st.markdown("#### Demo Accuracy Metrics")
    m1, m2, m3 = st.columns(3)
    m1.metric("Predictions Made", "143")
    m2.metric("Accuracy", "58.0%")
    m3.metric("vs. Random", "+8.0%")
    st.caption("These are illustrative demo numbers. Real metrics populate from logged predictions.")


model_dashboard_page()
