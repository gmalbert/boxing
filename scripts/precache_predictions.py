"""
KnockOutIQ — Pre-compute model predictions and store them to the database.

Run this after a data refresh so that Streamlit pages load instantly
(the Model Dashboard and Fight Card read from the DB instead of computing
predictions on-demand for every visitor).

Usage:
    python scripts/precache_predictions.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.db import Fight, Fighter, ModelPrediction, get_engine, get_session
from utils.feature_utils import build_features as _build_features_full
import models.logistic_model as lm
import models.xgboost_model as xgb


def precache_predictions() -> None:
    """Pre-compute and persist model predictions for all upcoming fights."""
    # Ensure tables exist
    get_engine()
    session = get_session()
    try:
        fights = (
            session.query(Fight)
            .filter(Fight.is_upcoming == True)  # noqa: E712
            .order_by(Fight.fight_date)
            .all()
        )
        print(f"[precache] {len(fights)} upcoming fight(s) found")

        if not fights:
            print("[precache] Nothing to do — no upcoming fights in DB.")
            return

        # Remove stale upcoming predictions before rewriting
        fight_ids = [f.id for f in fights]
        (
            session.query(ModelPrediction)
            .filter(ModelPrediction.fight_id.in_(fight_ids))
            .delete(synchronize_session=False)
        )
        session.commit()

        count = 0
        for fight in fights:
            fa = session.get(Fighter, fight.fighter_a_id)
            fb = session.get(Fighter, fight.fighter_b_id)
            if not fa or not fb:
                print(f"  [skip] fight_id={fight.id} — missing fighter record")
                continue

            # Skip women's bouts
            if getattr(fa, 'sex', 'M') == 'F' or getattr(fb, 'sex', 'M') == 'F':
                print(f"  [skip] {fa.name} vs {fb.name} — women's bout")
                continue

            features = _build_features_full(fa, fb, fight.fight_date, session,
                title_fight=fight.title_fight, weight_class=fight.weight_class)

            lr_prob = lm.predict_proba(features)
            xgb_prob, confidence = xgb.predict_proba(features)

            now = datetime.now(datetime.timezone.utc)

            session.add(ModelPrediction(
                fight_id=fight.id,
                model_version="logistic_v1",
                fighter_a_name=fa.name,
                fighter_b_name=fb.name,
                fighter_a_win_prob=lr_prob,
                confidence=0.5,
                predicted_at=now,
            ))
            session.add(ModelPrediction(
                fight_id=fight.id,
                model_version="xgboost_v1",
                fighter_a_name=fa.name,
                fighter_b_name=fb.name,
                fighter_a_win_prob=xgb_prob,
                confidence=confidence,
                predicted_at=now,
            ))

            print(
                f"  ✓ {fa.name} vs {fb.name} — "
                f"LR={lr_prob:.3f}  XGB={xgb_prob:.3f}  conf={confidence:.2f}"
            )
            count += 1

        session.commit()
        print(f"[precache] Done — {count * 2} prediction rows written")

    finally:
        session.close()


if __name__ == "__main__":
    precache_predictions()
