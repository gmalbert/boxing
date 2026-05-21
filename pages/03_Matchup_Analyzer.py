"""
KnockOutIQ — Matchup Analyzer Page
Head-to-head fighter comparison with model win probability.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.db import Fighter, Fight, get_session
from utils.odds_utils import fmt_american, calculate_edge, edge_label
import models.logistic_model as lm
import models.xgboost_model as xgb
from sqlalchemy import or_
from utils.page_utils import sidebar_header


# ─── Data Loaders ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def load_all_fighters() -> list[dict]:
    session = get_session()
    try:
        fighters = (
            session.query(Fighter)
            .filter(Fighter.sex != 'F')
            .order_by(Fighter.name)
            .all()
        )
        return [
            {
                "id": f.id, "name": f.name,
                "wins": f.wins or 0, "losses": f.losses or 0, "draws": f.draws or 0,
                "ko_wins": f.ko_wins or 0, "tko_wins": f.tko_wins or 0,
                "height_cm": f.height_cm, "reach_cm": f.reach_cm,
                "stance": f.stance or "Orthodox",
                "weight_class": f.weight_class or "N/A",
                "elo": f.elo_rating or 1500,
                "style_tag": f.style_tag,
                "nationality": f.nationality,
            }
            for f in fighters
        ]
    finally:
        session.close()


# ─── Feature Builders ─────────────────────────────────────────────────────────

def _build_features(fa: dict, fb: dict) -> dict:
    def win_pct(f):
        t = f["wins"] + f["losses"]
        return f["wins"] / t if t else 0.5

    def ko_pct(f):
        w = f["wins"] or 0
        k = (f["ko_wins"] or 0) + (f["tko_wins"] or 0)
        return k / w if w else 0.0

    return {
        "reach_diff": (fa["reach_cm"] or 0) - (fb["reach_cm"] or 0),
        "height_diff": (fa["height_cm"] or 0) - (fb["height_cm"] or 0),
        "age_diff": 0,
        "win_pct_diff": win_pct(fa) - win_pct(fb),
        "ko_pct_diff": ko_pct(fa) - ko_pct(fb),
        "elo_diff": fa["elo"] - fb["elo"],
        "days_since_last_fight_diff": 0,
        "opposition_quality_diff": 0,
        "is_southpaw_matchup": int(
            (fa["stance"] or "").lower() != (fb["stance"] or "").lower()
        ),
    }


# ─── Charts ───────────────────────────────────────────────────────────────────

def _gauge_chart(prob_a: float, name_a: str, name_b: str) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=prob_a * 100,
        number={"suffix": "%", "font": {"size": 32}},
        title={"text": f"{name_a} Win Probability"},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": "#f97316"},
            "steps": [
                {"range": [0, 40], "color": "#7f1d1d"},
                {"range": [40, 60], "color": "#78350f"},
                {"range": [60, 100], "color": "#14532d"},
            ],
            "threshold": {
                "line": {"color": "white", "width": 3},
                "thickness": 0.75,
                "value": 50,
            },
        },
    ))
    fig.update_layout(height=280, template="plotly_dark",
                      paper_bgcolor="rgba(0,0,0,0)")
    return fig


def _radar_chart(fa: dict, fb: dict) -> go.Figure:
    def win_pct(f):
        t = f["wins"] + f["losses"]
        return (f["wins"] / t * 100) if t else 50

    def ko_pct(f):
        w = f["wins"] or 1
        k = (f["ko_wins"] or 0) + (f["tko_wins"] or 0)
        return k / w * 100

    categories = ["Win %", "KO %", "Elo (norm)", "Reach", "Experience"]
    max_elo = 2000

    def scores(f):
        exp = min(100, (f["wins"] + f["losses"] + f["draws"]) * 2)
        return [
            win_pct(f),
            ko_pct(f),
            f["elo"] / max_elo * 100,
            min(100, (f["reach_cm"] or 170) / 220 * 100),
            exp,
        ]

    def _hex_to_rgba(hex_color: str, alpha: float) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    fig = go.Figure()
    for fighter, color in [(fa, "#f97316"), (fb, "#3b82f6")]:
        sc = scores(fighter)
        fig.add_trace(go.Scatterpolar(
            r=sc + [sc[0]], theta=categories + [categories[0]],
            fill="toself", fillcolor=_hex_to_rgba(color, 0.2),
            line=dict(color=color, width=2),
            name=fighter["name"],
        ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        height=320, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h"),
    )
    return fig


# ─── Demo Data ────────────────────────────────────────────────────────────────

_DEMO_FIGHTERS = [
    {"id": 1, "name": "Canelo Álvarez", "wins": 60, "losses": 2, "draws": 2,
     "ko_wins": 29, "tko_wins": 10, "height_cm": 173, "reach_cm": 179,
     "stance": "Orthodox", "weight_class": "Super Middleweight",
     "elo": 1830, "style_tag": "Boxer-Puncher", "nationality": "Mexico"},
    {"id": 2, "name": "Dmitry Bivol", "wins": 23, "losses": 1, "draws": 0,
     "ko_wins": 10, "tko_wins": 2, "height_cm": 178, "reach_cm": 183,
     "stance": "Orthodox", "weight_class": "Light Heavyweight",
     "elo": 1790, "style_tag": "Boxer", "nationality": "Russia"},
    {"id": 3, "name": "Terence Crawford", "wins": 40, "losses": 0, "draws": 0,
     "ko_wins": 20, "tko_wins": 9, "height_cm": 175, "reach_cm": 179,
     "stance": "Southpaw", "weight_class": "Welterweight",
     "elo": 1920, "style_tag": "Switch-hitter", "nationality": "USA"},
    {"id": 4, "name": "Errol Spence Jr.", "wins": 28, "losses": 1, "draws": 0,
     "ko_wins": 18, "tko_wins": 4, "height_cm": 178, "reach_cm": 188,
     "stance": "Orthodox", "weight_class": "Welterweight",
     "elo": 1850, "style_tag": "Pressure Fighter", "nationality": "USA"},
    {"id": 5, "name": "Oleksandr Usyk", "wins": 21, "losses": 0, "draws": 0,
     "ko_wins": 11, "tko_wins": 3, "height_cm": 191, "reach_cm": 196,
     "stance": "Southpaw", "weight_class": "Heavyweight",
     "elo": 1940, "style_tag": "Boxer", "nationality": "Ukraine"},
]


# ─── Page ─────────────────────────────────────────────────────────────────────

def matchup_analyzer_page():
    sidebar_header()
    st.title("⚔️ Matchup Analyzer")
    st.caption("Head-to-head comparison · Model win probability · Style matchup")

    fighters = load_all_fighters()
    demo_mode = len(fighters) == 0

    if demo_mode:
        st.info("Database not yet populated. Showing demo data.", icon="ℹ️")
        fighters = _DEMO_FIGHTERS

    fighter_names = [f["name"] for f in fighters]

    col1, col2 = st.columns(2)
    with col1:
        name_a = st.selectbox("Fighter A", fighter_names, index=0, key="fa")
    with col2:
        default_b = 1 if len(fighter_names) > 1 else 0
        name_b = st.selectbox("Fighter B", fighter_names, index=default_b, key="fb")

    if name_a == name_b:
        st.warning("Please select two different fighters.")
        return

    fa = next(f for f in fighters if f["name"] == name_a)
    fb = next(f for f in fighters if f["name"] == name_b)
    features = _build_features(fa, fb)
    prob_a = lm.predict_proba(features)
    prob_b = 1 - prob_a
    xgb_prob_a, confidence = xgb.predict_proba(features)

    # Optional DK odds input
    st.markdown("---")
    st.markdown("#### Optional: Enter Current DraftKings Odds")
    dk_col1, dk_col2 = st.columns(2)
    with dk_col1:
        dk_a = st.number_input(f"{fa['name']} DK odds", value=-110, step=5, key="dk_a")
    with dk_col2:
        dk_b = st.number_input(f"{fb['name']} DK odds", value=-110, step=5, key="dk_b")

    edge_a = calculate_edge(prob_a, dk_a)
    edge_b = calculate_edge(prob_b, dk_b)
    label_a, color_a = edge_label(edge_a)
    label_b, color_b = edge_label(edge_b)

    st.markdown("---")

    # ── Probability Gauge ─────────────────────────────────────────────────
    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(_gauge_chart(prob_a, fa["name"], fb["name"]), use_container_width=True)
    with g2:
        st.plotly_chart(_radar_chart(fa, fb), use_container_width=True)

    # ── Model Results ─────────────────────────────────────────────────────
    st.markdown("### Model Predictions")
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric(f"{fa['name']} (LogReg)", f"{prob_a:.1%}")
    mc2.metric(f"{fb['name']} (LogReg)", f"{prob_b:.1%}")
    mc3.metric(f"{fa['name']} (XGBoost)", f"{xgb_prob_a:.1%}")
    mc4.metric("XGB Confidence", f"{confidence:.0%}")

    # ── Edge Analysis ─────────────────────────────────────────────────────
    st.markdown("### Edge vs. DraftKings")
    e1, e2 = st.columns(2)
    with e1:
        st.markdown(f"**{fa['name']}:** Edge `{edge_a:+.1%}` — {label_a}")
    with e2:
        st.markdown(f"**{fb['name']}:** Edge `{edge_b:+.1%}` — {label_b}")

    # ── Side-by-Side Stats ────────────────────────────────────────────────
    st.markdown("### Fighter Comparison")
    stats = {
        "Record": (
            f"{fa['wins']}-{fa['losses']}-{fa['draws']}",
            f"{fb['wins']}-{fb['losses']}-{fb['draws']}",
        ),
        "Elo Rating": (f"{fa['elo']:.0f}", f"{fb['elo']:.0f}"),
        "Stance": (fa["stance"], fb["stance"]),
        "Height (cm)": (str(fa["height_cm"] or "N/A"), str(fb["height_cm"] or "N/A")),
        "Reach (cm)": (str(fa["reach_cm"] or "N/A"), str(fb["reach_cm"] or "N/A")),
        "Style": (fa["style_tag"] or "N/A", fb["style_tag"] or "N/A"),
        "Nationality": (fa["nationality"] or "N/A", fb["nationality"] or "N/A"),
        "Weight Class": (fa["weight_class"], fb["weight_class"]),
    }
    table_data = [{"Stat": k, fa["name"]: v[0], fb["name"]: v[1]} for k, v in stats.items()]
    df = pd.DataFrame(table_data)

    def highlight_diff(row):
        styles = ["", "", ""]
        try:
            va, vb = float(row.iloc[1]), float(row.iloc[2])
            if va > vb:
                styles[1] = "background-color: #14532d"
            elif vb > va:
                styles[2] = "background-color: #14532d"
        except (ValueError, TypeError):
            pass
        return styles

    st.dataframe(df.style.apply(highlight_diff, axis=1), use_container_width=True, hide_index=True)

    # ── Stance Matchup Note ───────────────────────────────────────────────
    if fa["stance"] != fb["stance"]:
        st.info(
            f"**Southpaw matchup** — {fa['name']} ({fa['stance']}) vs {fb['name']} ({fb['stance']}). "
            "Orthodox vs. Southpaw matchups often produce awkward angles and can favour the counter-puncher.",
            icon="🔄",
        )


matchup_analyzer_page()
