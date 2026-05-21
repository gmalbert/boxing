"""
KnockOutIQ — Historical Fight Database Page
Searchable archive of fights with stats and trends.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data.db import Fight, Fighter, FightStats, get_session
from sqlalchemy import or_, func
from utils.page_utils import sidebar_header


# ─── Data Loaders ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def load_fight_database(
    weight_class: str | None = None,
    year: int | None = None,
    method: str | None = None,
    title_only: bool = False,
    limit: int = 200,
) -> pd.DataFrame:
    session = get_session()
    try:
        q = session.query(Fight).filter(Fight.is_upcoming == False)
        if weight_class:
            q = q.filter(Fight.weight_class == weight_class)
        if year:
            q = q.filter(func.strftime("%Y", Fight.fight_date) == str(year))
        if method:
            q = q.filter(Fight.method == method)
        if title_only:
            q = q.filter(Fight.title_fight == True)
        q = q.order_by(Fight.fight_date.desc()).limit(limit)
        fights = q.all()

        rows = []
        for f in fights:
            fa = session.get(Fighter, f.fighter_a_id)
            fb = session.get(Fighter, f.fighter_b_id)
            winner = ""
            if f.result == "A" and fa:
                winner = fa.name
            elif f.result == "B" and fb:
                winner = fb.name
            elif f.result in ("draw", "NC"):
                winner = "Draw/NC"

            rows.append({
                "Date": f.fight_date,
                "Fighter A": fa.name if fa else "Unknown",
                "Fighter B": fb.name if fb else "Unknown",
                "Winner": winner,
                "Method": f.method or "N/A",
                "Round": f.round_ended or "N/A",
                "Weight Class": f.weight_class or "N/A",
                "Title 🏆": "Yes" if f.title_fight else "",
                "Event": f.event_name or "",
                "_fight_id": f.id,
            })
        return pd.DataFrame(rows)
    finally:
        session.close()


@st.cache_data(ttl=600, show_spinner=False)
def load_filter_options() -> dict:
    session = get_session()
    try:
        weight_classes = [
            r[0] for r in session.query(Fight.weight_class).distinct().all()
            if r[0]
        ]
        years = sorted(set(
            f.fight_date.year for f in session.query(Fight).filter(Fight.fight_date.isnot(None)).all()
            if not f.is_upcoming
        ), reverse=True)
        methods = [
            r[0] for r in session.query(Fight.method).distinct().all()
            if r[0]
        ]
        return {
            "weight_classes": sorted(weight_classes),
            "years": years,
            "methods": sorted(methods),
        }
    finally:
        session.close()


@st.cache_data(ttl=600, show_spinner=False)
def load_trend_data() -> pd.DataFrame:
    session = get_session()
    try:
        fights = (
            session.query(Fight)
            .filter(
                Fight.is_upcoming == False,
                Fight.fight_date.isnot(None),
                Fight.method.isnot(None),
            )
            .all()
        )
        rows = []
        for f in fights:
            rows.append({
                "year": f.fight_date.year if f.fight_date else None,
                "method": f.method or "N/A",
                "weight_class": f.weight_class or "N/A",
                "round_ended": f.round_ended or 0,
                "title_fight": f.title_fight,
            })
        return pd.DataFrame(rows)
    finally:
        session.close()


# ─── Charts ───────────────────────────────────────────────────────────────────

def _ko_rate_by_weight(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure().add_annotation(text="No data", showarrow=False)
    df = df.copy()
    df["is_ko"] = df["method"].isin(["KO", "TKO", "RTD"])
    by_class = df.groupby("weight_class")["is_ko"].mean().reset_index()
    by_class.columns = ["Weight Class", "KO Rate"]
    by_class = by_class.sort_values("KO Rate", ascending=False)
    fig = px.bar(by_class, x="Weight Class", y="KO Rate",
                 color="KO Rate", color_continuous_scale="Reds",
                 title="KO/TKO Rate by Weight Class")
    fig.update_layout(
        height=350, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.3)",
        yaxis_tickformat=".0%",
    )
    return fig


def _method_trend(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()
    df = df.copy()
    df["is_finish"] = df["method"].isin(["KO", "TKO", "RTD"])
    trend = df.groupby("year")["is_finish"].mean().reset_index()
    trend.columns = ["Year", "Finish Rate"]
    fig = px.line(trend, x="Year", y="Finish Rate",
                  title="Finish Rate Trend by Year", markers=True)
    fig.update_layout(
        height=300, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.3)",
        yaxis_tickformat=".0%",
    )
    return fig


def _avg_rounds_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()
    df = df[df["round_ended"] > 0]
    by_class = df.groupby("weight_class")["round_ended"].mean().reset_index()
    by_class.columns = ["Weight Class", "Avg Round of Stoppage"]
    fig = px.bar(by_class.sort_values("Avg Round of Stoppage"),
                 x="Weight Class", y="Avg Round of Stoppage",
                 title="Average Round of Stoppage by Weight Class")
    fig.update_layout(
        height=320, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.3)",
    )
    return fig


# ─── Page ─────────────────────────────────────────────────────────────────────

def fight_database_page():
    sidebar_header()
    st.title("📚 Fight Database")
    st.caption("Search & browse 10 years of boxing history · Stats · Trends")

    tab_search, tab_trends = st.tabs(["Search Fights", "Trends & Analytics"])

    with tab_search:
        _tab_search()

    with tab_trends:
        _tab_trends()


def _tab_search():
    st.subheader("Search Historical Fights")

    opts = load_filter_options()
    demo_mode = len(opts["years"]) == 0

    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        wc_options = ["All"] + (opts["weight_classes"] if not demo_mode else
                                ["Heavyweight", "Lightweight", "Welterweight", "Middleweight"])
        weight_class = st.selectbox("Weight Class", wc_options)
    with col2:
        year_options = ["All"] + ([str(y) for y in opts["years"]] if not demo_mode else
                                   [str(y) for y in range(2024, 2015, -1)])
        year = st.selectbox("Year", year_options)
    with col3:
        method_options = ["All"] + (opts["methods"] if not demo_mode else
                                    ["KO", "TKO", "UD", "MD", "SD", "DQ"])
        method = st.selectbox("Method", method_options)
    with col4:
        title_only = st.checkbox("Title Fights Only")

    fighter_search = st.text_input("Search by fighter name", placeholder="e.g. Crawford, Canelo…")

    if demo_mode:
        st.info("Database not yet populated. Run the backfill script to load 10 years of data.", icon="ℹ️")
        _demo_fights_table()
        return

    df = load_fight_database(
        weight_class=weight_class if weight_class != "All" else None,
        year=int(year) if year != "All" else None,
        method=method if method != "All" else None,
        title_only=title_only,
    )

    if fighter_search:
        mask = (
            df["Fighter A"].str.contains(fighter_search, case=False, na=False) |
            df["Fighter B"].str.contains(fighter_search, case=False, na=False)
        )
        df = df[mask]

    if df.empty:
        st.warning("No fights match your criteria.")
        return

    st.markdown(f"**{len(df)} fight(s) found**")

    display_df = df.drop(columns=["_fight_id"])

    def color_method(val):
        if val in ("KO", "TKO", "RTD"):
            return "color: #ef4444; font-weight: bold"
        elif val in ("UD", "MD", "SD"):
            return "color: #3b82f6"
        return ""

    styled = display_df.style.map(color_method, subset=["Method"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Download
    csv = display_df.to_csv(index=False)
    st.download_button(
        "⬇️ Download CSV",
        data=csv,
        file_name="knockoutiq_fights.csv",
        mime="text/csv",
    )


def _demo_fights_table():
    demo = [
        {"Date": "2024-09-14", "Fighter A": "Oleksandr Usyk", "Fighter B": "Tyson Fury",
         "Winner": "Oleksandr Usyk", "Method": "UD", "Round": 12,
         "Weight Class": "Heavyweight", "Title 🏆": "Yes", "Event": "Fury vs. Usyk 2"},
        {"Date": "2023-05-20", "Fighter A": "Dmitry Bivol", "Fighter B": "Canelo Álvarez",
         "Winner": "Dmitry Bivol", "Method": "UD", "Round": 12,
         "Weight Class": "Light Heavyweight", "Title 🏆": "Yes", "Event": "Bivol vs. Canelo"},
        {"Date": "2023-07-29", "Fighter A": "Terence Crawford", "Fighter B": "Errol Spence Jr.",
         "Winner": "Terence Crawford", "Method": "TKO", "Round": 9,
         "Weight Class": "Welterweight", "Title 🏆": "Yes", "Event": "Crawford vs. Spence"},
    ]
    st.caption("Demo data — run backfill to load real fights")
    st.dataframe(pd.DataFrame(demo), use_container_width=True, hide_index=True)


def _tab_trends():
    st.subheader("Boxing Trends & Analytics")
    df = load_trend_data()

    if df.empty:
        st.info("No historical data yet. Run `python scripts/fetch_historical_data.py backfill` to populate.", icon="ℹ️")
        _demo_trends()
        return

    # Method distribution pie
    method_counts = df["method"].value_counts().reset_index()
    method_counts.columns = ["Method", "Count"]

    t1, t2 = st.columns(2)
    with t1:
        fig_pie = px.pie(method_counts, names="Method", values="Count",
                         title="Fight Result Methods (All Time)",
                         color_discrete_sequence=px.colors.qualitative.Bold)
        fig_pie.update_layout(height=300, template="plotly_dark",
                               paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_pie, use_container_width=True)
    with t2:
        st.plotly_chart(_method_trend(df), use_container_width=True)

    st.plotly_chart(_ko_rate_by_weight(df), use_container_width=True)
    st.plotly_chart(_avg_rounds_chart(df), use_container_width=True)

    # Title fight stats
    title_pct = df["title_fight"].mean() * 100 if not df.empty else 0
    st.metric("Title Fight %", f"{title_pct:.1f}%")


def _demo_trends():
    st.markdown("#### Demo Trend Charts")
    demo_data = {
        "method": ["KO"] * 30 + ["TKO"] * 25 + ["UD"] * 35 + ["MD"] * 6 + ["SD"] * 4,
        "weight_class": (["Heavyweight"] * 20 + ["Welterweight"] * 20 +
                         ["Lightweight"] * 20 + ["Middleweight"] * 20 + ["Featherweight"] * 20),
        "year": ([2020] * 20 + [2021] * 20 + [2022] * 20 + [2023] * 20 + [2024] * 20),
        "round_ended": [7] * 30 + [10] * 25 + [12] * 45,
        "title_fight": [True] * 25 + [False] * 75,
    }
    df_demo = pd.DataFrame(demo_data)
    t1, t2 = st.columns(2)
    method_counts = pd.DataFrame(df_demo["method"].value_counts()).reset_index()
    method_counts.columns = ["Method", "Count"]
    with t1:
        fig = px.pie(method_counts, names="Method", values="Count",
                     title="Fight Result Methods (Demo)")
        fig.update_layout(height=280, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
    with t2:
        st.plotly_chart(_ko_rate_by_weight(df_demo), use_container_width=True)
    st.caption("Demo data — connect APIs and run backfill for real trends")


fight_database_page()
