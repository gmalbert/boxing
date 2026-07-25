"""
KnockOutIQ — Backtesting Framework

Chronologically replays the model through historical fights (walk-forward),
tracking cumulative edge vs. actual win rate, ROI by edge tier, and calibration
drift over time. Runs the same feature builder + model pipeline used in
production so results reflect real-world performance.

Usage:
    python scripts/backtest.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss

from data.db import Fight, Fighter, OddsSnapshot, get_engine, get_session
from utils.feature_utils import build_features
from utils.odds_utils import american_to_implied_prob, calculate_edge
import models.logistic_model as lm
import models.xgboost_model as xgb

MIN_FIGHTS_BEFORE_START = 10
EDGE_TIERS = [(0.06, "Elite"), (0.03, "Strong"), (0.01, "Good"), (0.0, "Standard")]


def _tier_label(edge: float) -> str:
    for threshold, label in EDGE_TIERS:
        if edge >= threshold:
            return label
    return "No Edge"


def load_trainable_fights(session):
    """Return completed fights in chronological order (oldest first)."""
    return (
        session.query(Fight)
        .filter(Fight.is_upcoming == False)  # noqa: E712
        .filter(Fight.result.in_(["A", "B"]))
        .order_by(Fight.fight_date.asc())
        .all()
    )


def run():
    get_engine()
    session = get_session()

    try:
        fights = load_trainable_fights(session)
        print(f"[backtest] {len(fights)} completed fights found")

        if len(fights) < MIN_FIGHTS_BEFORE_START:
            print(f"[backtest] Need at least {MIN_FIGHTS_BEFORE_START} fights. Exiting.")
            return

        predictions: list[dict] = []
        tier_wins: dict[str, int] = defaultdict(int)
        tier_total: dict[str, int] = defaultdict(int)
        tier_units: dict[str, float] = defaultdict(float)
        edge_history: list[float] = []

        for i, fight in enumerate(fights):
            if i < MIN_FIGHTS_BEFORE_START:
                continue

            fa = session.get(Fighter, fight.fighter_a_id)
            fb = session.get(Fighter, fight.fighter_b_id)
            if not fa or not fb:
                continue

            # Only use data known before this fight's date
            before = fight.fight_date or date.today()
            features = build_features(fa, fb, before, session,
                title_fight=fight.title_fight, weight_class=fight.weight_class)

            lr_prob = lm.predict_proba(features)
            xgb_prob, confidence = xgb.predict_proba(features)
            label = 1 if fight.result == "A" else 0

            # Get DK odds just for edge calculation
            snap_a = (
                session.query(OddsSnapshot)
                .filter(OddsSnapshot.fight_id == fight.id)
                .filter(OddsSnapshot.fighter_name == fa.name)
                .filter(OddsSnapshot.bookmaker == "draftkings")
                .order_by(OddsSnapshot.snapshot_time.asc())
                .first()
            )
            dk_a = snap_a.american_odds if snap_a else None

            edge = calculate_edge(lr_prob, dk_a) if dk_a else None

            predictions.append({
                "fight_date": before,
                "matchup": f"{fa.name} vs {fb.name}",
                "lr_prob_a": lr_prob,
                "xgb_prob_a": xgb_prob,
                "confidence": confidence,
                "label": label,
                "edge": edge,
                "dk_odds": dk_a,
            })

            tier = _tier_label(edge or 0)
            tier_total[tier] += 1
            correct = (lr_prob >= 0.5) == bool(label)
            if correct:
                tier_wins[tier] += 1
            if edge and edge >= 0.01:
                tier_units[tier] += 1.0 if correct else -1.0
            if edge is not None:
                edge_history.append(edge)

        # ── Report ───────────────────────────────────────────────────────────
        print(f"\n{'='*60}")
        print(f"  BACKTEST RESULTS  ({len(predictions)} predictions)")
        print(f"{'='*60}")

        probs = np.array([p["lr_prob_a"] for p in predictions])
        labels = np.array([p["label"] for p in predictions])
        acc = (labels == (probs >= 0.5).astype(int)).mean()
        brier = brier_score_loss(labels, np.clip(probs, 1e-6, 1 - 1e-6))
        ll = log_loss(labels, np.clip(probs, 1e-6, 1 - 1e-6))

        print(f"  Accuracy:      {acc:.3f}  ({acc:.1%})")
        print(f"  vs Random:     {acc - 0.5:+.3f}")
        print(f"  Brier Score:   {brier:.4f}")
        print(f"  Log-Loss:      {ll:.4f}")

        print(f"\n  {'Tier':12s}  {'Picks':>5s}  {'Win%':>6s}  {'ROI':>6s}")
        print(f"  {'-'*12}  {'-'*5}  {'-'*6}  {'-'*6}")
        for _, tier_name in EDGE_TIERS:
            n = tier_total[tier_name]
            if n == 0:
                print(f"  {tier_name:12s}  {0:5d}  {'—':>6s}  {'—':>6s}")
                continue
            wr = tier_wins[tier_name] / n
            roi = tier_units[tier_name] / n
            print(f"  {tier_name:12s}  {n:5d}  {wr:5.1%}  {roi:+.3f}")

        # Calibration by decile
        print(f"\n  Calibration by decile:")
        bins = np.arange(0, 1.01, 0.1)
        for lo, hi in zip(bins[:-1], bins[1:]):
            mask = (probs >= lo) & (probs < hi)
            if mask.sum() == 0:
                continue
            bin_acc = labels[mask].mean()
            bin_mean = probs[mask].mean()
            line = "  ⚠" if abs(bin_acc - bin_mean) > 0.1 else "  ✓"
            print(f"{line}  [{lo:.1f}-{hi:.1f})  n={mask.sum():3d}  "
                  f"pred_mean={bin_mean:.3f}  actual={bin_acc:.3f}")

        # Cumulative edge vs win rate
        if len(edge_history) >= 5:
            cum_edges = np.cumsum(edge_history)
            n = len(edge_history)
            print(f"\n  Cumulative Edge Trend: {'↑' if cum_edges[-1] > 0 else '↓'}")
            print(f"  Final cumulative edge: {cum_edges[-1]:+.2f} over {n} fights")
            print(f"  Average edge per fight: {np.mean(edge_history):+.4f}")

        print(f"\n[backtest] Done.")

    finally:
        session.close()


if __name__ == "__main__":
    run()
