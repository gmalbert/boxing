"""
KnockOutIQ — Model Training Pipeline

Loads all completed fights with definitive results (result = 'A' or 'B') from
the database, builds feature vectors using the shared feature_utils module,
trains the logistic regression and XGBoost models with calibration and
cross-validation, logs evaluation metrics, and saves pickle files to
data_files/models/.

Usage:
    python scripts/train_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.model_selection import StratifiedKFold, cross_val_score

from data.db import Fight, Fighter, get_engine, get_session
from utils.feature_utils import build_features
import models.logistic_model as lm
import models.xgboost_model as xgb_mod

# Refuse to train if fewer than this many samples exist (would overfit badly)
MIN_TRAINING_SAMPLES = 20


# ─── Data loading ─────────────────────────────────────────────────────────────

def load_training_data(session) -> tuple[pd.DataFrame, pd.Series]:
    """
    Build a labeled feature dataset from all completed fights.

    Each fight produces two rows (mirror augmentation):
      - Original:  features(A vs B), label=1 if A won
      - Mirrored:  negated diffs (B vs A perspective), label=1 if B won

    This doubles the dataset and removes the positional bias from how
    fight records are stored.
    """
    fights = (
        session.query(Fight)
        .filter(Fight.is_upcoming == False)   # noqa: E712
        .filter(Fight.result.in_(["A", "B"]))
        .order_by(Fight.fight_date)
        .all()
    )

    rows: list[dict] = []
    labels: list[int] = []

    for fight in fights:
        fa = session.get(Fighter, fight.fighter_a_id)
        fb = session.get(Fighter, fight.fighter_b_id)
        if not fa or not fb:
            continue

        # Skip women's bouts (same filter as precache_predictions.py)
        if getattr(fa, "sex", "M") == "F" or getattr(fb, "sex", "M") == "F":
            continue

        features = build_features(fa, fb, fight.fight_date, session,
            title_fight=fight.title_fight, weight_class=fight.weight_class)
        label = 1 if fight.result == "A" else 0
        rows.append(features)
        labels.append(label)

        # Mirror: swap A↔B by negating all directional diffs
        mirror = {
            k: (-v if k != "is_southpaw_matchup" else v)
            for k, v in features.items()
        }
        rows.append(mirror)
        labels.append(1 - label)

    return pd.DataFrame(rows), pd.Series(labels, dtype=int)


# ─── Training routine ─────────────────────────────────────────────────────────

def train_and_evaluate() -> None:
    """
    Full training routine:

    1. Load data from DB
    2. Chronological 80/20 train/test split
    3. Train logistic regression (with Platt-scaling calibration)
    4. Train XGBoost (with Platt-scaling calibration)
    5. Report holdout accuracy, Brier score, and log-loss
    6. Run 5-fold stratified cross-validation for variance estimate
    7. Save pickle files to data_files/models/
    """
    get_engine()
    session = get_session()

    try:
        print("[train] Loading training data from DB...")
        X, y = load_training_data(session)
        n = len(X)
        print(f"[train] {n} samples loaded  "
              f"({int(y.sum())} class-A wins, {int((1 - y).sum())} class-B wins)")

        if n < MIN_TRAINING_SAMPLES:
            print(
                f"[train] WARNING: Only {n} samples — minimum {MIN_TRAINING_SAMPLES} required. "
                "Skipping training. Add more historical fight data and re-run."
            )
            return

        # ── Train / test split (chronological, no shuffle) ────────────────────
        split_idx = int(n * 0.8)
        X_train = X.iloc[:split_idx].copy()
        X_test  = X.iloc[split_idx:].copy()
        y_train = y.iloc[:split_idx].copy()
        y_test  = y.iloc[split_idx:].copy()
        print(f"[train] Train: {len(X_train)} samples | Test: {len(X_test)} samples")

        n_folds = min(5, max(2, len(X_train) // 4))
        cv = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)

        # ── Logistic Regression ───────────────────────────────────────────────
        print("\n[train] === Logistic Regression ===")
        lr_model = lm.train(X_train, y_train)

        if len(X_test) >= 4:
            lr_preds = lr_model.predict_proba(X_test[lm.FEATURE_COLS])[:, 1]
            _print_metrics("Holdout", y_test, lr_preds)

        cv_scores = cross_val_score(
            lm._build_pipeline(), X[lm.FEATURE_COLS], y,
            cv=cv, scoring="accuracy",
        )
        print(f"  {n_folds}-fold CV -> accuracy = {cv_scores.mean():.3f} +/- {cv_scores.std():.3f}")

        # ── XGBoost ───────────────────────────────────────────────────────────
        print("\n[train] === XGBoost ===")
        try:
            xgb_mod.train(X_train, y_train)
            bundle = xgb_mod.load()
            if bundle and len(X_test) >= 4:
                feat_cols = bundle["features"]
                xgb_preds = bundle["model"].predict_proba(X_test[feat_cols])[:, 1]
                _print_metrics("Holdout", y_test, xgb_preds)
        except ImportError:
            print("  [skip] xgboost not installed — XGBoost training skipped")

        print("\n[train] Pickle files saved -> data_files/models/")
        print("[train] Done.")

    finally:
        session.close()


def _print_metrics(label: str, y_true: pd.Series, y_pred: np.ndarray) -> None:
    acc    = accuracy_score(y_true, (y_pred >= 0.5).astype(int))
    brier  = brier_score_loss(y_true, y_pred)
    logloss = log_loss(y_true, y_pred)
    print(f"  {label:10s} -> acc={acc:.3f}  brier={brier:.4f}  logloss={logloss:.4f}")


if __name__ == "__main__":
    train_and_evaluate()
