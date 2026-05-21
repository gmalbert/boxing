"""
KnockOutIQ — Logistic Regression Baseline Model
Interpretable baseline for win prediction. Trained on fighter features.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

_MODEL_DIR = Path(__file__).parent.parent / "data_files" / "models"
_MODEL_PATH = _MODEL_DIR / "logistic_model.pkl"

FEATURE_COLS = [
    "reach_diff",
    "height_diff",
    "age_diff",
    "win_pct_diff",
    "ko_pct_diff",
    "elo_diff",
    "days_since_last_fight_diff",
    "opposition_quality_diff",
    "is_southpaw_matchup",
]


def _build_pipeline() -> Pipeline:
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=1000, C=0.5, random_state=42)),
    ])


def train(X: pd.DataFrame, y: pd.Series) -> Pipeline:
    """Train the logistic model and save to disk."""
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    pipe = _build_pipeline()
    pipe.fit(X[FEATURE_COLS], y)
    joblib.dump(pipe, _MODEL_PATH)
    return pipe


def load() -> Optional[Pipeline]:
    """Load saved model from disk, or return None if not found."""
    if _MODEL_PATH.exists():
        return joblib.load(_MODEL_PATH)
    return None


def predict_proba(
    features: dict,
    model: Optional[Pipeline] = None,
) -> float:
    """Return win probability for fighter_a given a feature dict."""
    if model is None:
        model = load()
    if model is None:
        return _heuristic_prob(features)

    row = pd.DataFrame([{col: features.get(col, 0.0) for col in FEATURE_COLS}])
    return float(model.predict_proba(row)[0][1])


def _heuristic_prob(features: dict) -> float:
    """
    Simple weighted heuristic when model not yet trained.
    Used for demo purposes only.
    """
    weights = {
        "elo_diff": 0.35,
        "win_pct_diff": 0.25,
        "reach_diff": 0.15,
        "ko_pct_diff": 0.10,
        "age_diff": -0.08,
        "opposition_quality_diff": 0.07,
    }
    score = sum(
        features.get(k, 0.0) * w for k, w in weights.items()
    )
    # Sigmoid to probability
    prob = 1 / (1 + np.exp(-score / 100))
    return float(np.clip(prob, 0.05, 0.95))
