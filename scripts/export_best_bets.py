"""
Export daily best bets for the Sports Picks Grid aggregator.

Queries the KnockOutIQ SQLite database for upcoming fights, runs the
logistic model (or an Elo heuristic fallback), compares against the
latest DraftKings odds snapshot, and writes data_files/best_bets_today.json.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Allow imports from repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import desc
from sqlalchemy.orm import Session

try:
    from data.db import Base, Fight, Fighter, OddsSnapshot, ModelPrediction
    from config import DB_URL
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    DB_AVAILABLE = True
except Exception as e:
    print(f"[boxing export] DB import error: {e}")
    DB_AVAILABLE = False

OUT_PATH = ROOT / "data_files" / "best_bets_today.json"
LOOKAHEAD_DAYS = 14   # fights can be announced further ahead
MIN_EDGE = 0.03       # 3% minimum edge


def _american_to_prob(odds: int) -> float:
    """Convert American moneyline to implied probability (without vig)."""
    if odds is None:
        return 0.5
    if odds > 0:
        return 100.0 / (odds + 100.0)
    else:
        return abs(odds) / (abs(odds) + 100.0)


def _prob_to_american(prob: float) -> int:
    """Convert win probability to approximate American odds."""
    prob = max(0.01, min(0.99, prob))
    if prob >= 0.5:
        return -round(prob / (1 - prob) * 100)
    else:
        return round((1 - prob) / prob * 100)


def _elo_win_prob(elo_a: float, elo_b: float) -> float:
    """Standard Elo expected score for fighter A."""
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))


def _tier(edge: float) -> str:
    if edge >= 0.06:
        return "Elite"
    elif edge >= 0.03:
        return "Strong"
    elif edge >= 0.01:
        return "Good"
    return "Standard"


def get_bets(session: Session) -> list[dict]:
    today = date.today()
    cutoff = today + timedelta(days=LOOKAHEAD_DAYS)
    bets: list[dict] = []

    fights = (
        session.query(Fight)
        .filter(Fight.is_upcoming == True)
        .filter(Fight.fight_date >= today)
        .filter(Fight.fight_date <= cutoff)
        .all()
    )

    for fight in fights:
        fa: Fighter | None = session.get(Fighter, fight.fighter_a_id)
        fb: Fighter | None = session.get(Fighter, fight.fighter_b_id)
        if not fa or not fb:
            continue

        # Try model prediction first (most recent)
        pred = (
            session.query(ModelPrediction)
            .filter(ModelPrediction.fight_id == fight.id)
            .order_by(desc(ModelPrediction.predicted_at))
            .first()
        )

        if pred and pred.fighter_a_win_prob is not None:
            model_prob_a = float(pred.fighter_a_win_prob)
        else:
            # Fall back to Elo heuristic
            elo_a = fa.elo_rating or 1500.0
            elo_b = fb.elo_rating or 1500.0
            model_prob_a = _elo_win_prob(elo_a, elo_b)

        # Latest odds snapshot for fighter A
        snap_a = (
            session.query(OddsSnapshot)
            .filter(OddsSnapshot.fight_id == fight.id)
            .filter(OddsSnapshot.fighter_name == fa.name)
            .order_by(desc(OddsSnapshot.snapshot_time))
            .first()
        )
        snap_b = (
            session.query(OddsSnapshot)
            .filter(OddsSnapshot.fight_id == fight.id)
            .filter(OddsSnapshot.fighter_name == fb.name)
            .order_by(desc(OddsSnapshot.snapshot_time))
            .first()
        )

        # Determine the better side to bet
        if snap_a and snap_a.american_odds is not None:
            implied_a = _american_to_prob(snap_a.american_odds)
            edge_a = model_prob_a - implied_a
        else:
            implied_a = None
            edge_a = 0.0

        model_prob_b = 1.0 - model_prob_a
        if snap_b and snap_b.american_odds is not None:
            implied_b = _american_to_prob(snap_b.american_odds)
            edge_b = model_prob_b - implied_b
        else:
            implied_b = None
            edge_b = 0.0

        # Pick the side with the better edge
        if edge_a >= edge_b and edge_a >= MIN_EDGE:
            pick_name = fa.name
            confidence = round(model_prob_a, 4)
            edge = round(edge_a, 4)
            odds = snap_a.american_odds if snap_a else None
        elif edge_b >= MIN_EDGE:
            pick_name = fb.name
            confidence = round(model_prob_b, 4)
            edge = round(edge_b, 4)
            odds = snap_b.american_odds if snap_b else None
        else:
            continue  # No edge on either side

        game_date = fight.fight_date.isoformat() if fight.fight_date else date.today().isoformat()
        game_str = f"{fa.name} vs {fb.name}"
        event_name = fight.event_name or ""
        weight_class = fight.weight_class or ""
        notes_parts = [p for p in [event_name, weight_class] if p]

        bets.append({
            "game_date":  game_date,
            "game":       game_str,
            "game_time":  "",
            "bet_type":   "moneyline",
            "pick":       pick_name,
            "confidence": confidence,
            "edge":       edge,
            "odds":       odds,
            "tier":       _tier(edge),
            "notes":      " | ".join(notes_parts),
        })

    return bets


def main() -> None:
    if not DB_AVAILABLE:
        print("[boxing export] DB not available — writing empty output")
        bets: list[dict] = []
    else:
        with SessionLocal() as session:
            bets = get_bets(session)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "sport":         "Boxing",
            "generated_at":  datetime.now(timezone.utc).isoformat(),
            "model_version": "1.0.0",
            "season":        str(datetime.now(timezone.utc).year),
        },
        "bets": bets,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"[boxing export] Wrote {len(bets)} bets → {OUT_PATH}")


if __name__ == "__main__":
    main()
