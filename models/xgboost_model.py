"""
KnockOutIQ — XGBoost Ensemble Model
Primary prediction model. Handles non-linear interactions between fighter features.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd

try:
    from xgboost import XGBClassifier
    _XGB_AVAILABLE = True
except ImportError:
    _XGB_AVAILABLE = False

from models.logistic_model import FEATURE_COLS, _heuristic_prob

_MODEL_DIR = Path(__file__).parent.parent / "data_files" / "models"
_MODEL_PATH = _MODEL_DIR / "xgboost_model.pkl"
_VERSION = "1.0.0"

EXTENDED_FEATURE_COLS = FEATURE_COLS + [
    "rolling_win_rate_diff",
    "recent_ko_pct_diff",
    "avg_rounds_fought_diff",
    "title_fight",
    "weight_class_encoded",
]


def _build_model():
    if not _XGB_AVAILABLE:
        raise ImportError("xgboost is not installed.")
    return XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
    )


def train(X: pd.DataFrame, y: pd.Series) -> object:
    """Train and save the XGBoost model."""
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    available_cols = [c for c in EXTENDED_FEATURE_COLS if c in X.columns]
    model = _build_model()
    model.fit(X[available_cols], y)
    joblib.dump({"model": model, "features": available_cols, "version": _VERSION}, _MODEL_PATH)
    return model


def load() -> Optional[dict]:
    """Load saved model bundle from disk."""
    if _MODEL_PATH.exists():
        return joblib.load(_MODEL_PATH)
    return None


def predict_proba(
    features: dict,
    bundle: Optional[dict] = None,
) -> tuple[float, float]:
    """
    Return (win_prob, confidence) for fighter_a.
    Confidence is based on how far the probability is from 0.5.
    """
    if bundle is None:
        bundle = load()

    if bundle is None or not _XGB_AVAILABLE:
        prob = _heuristic_prob(features)
        confidence = abs(prob - 0.5) * 2
        return prob, confidence

    model = bundle["model"]
    feat_cols = bundle["features"]
    row = pd.DataFrame([{col: features.get(col, 0.0) for col in feat_cols}])
    prob = float(model.predict_proba(row)[0][1])
    confidence = abs(prob - 0.5) * 2
    return float(np.clip(prob, 0.05, 0.95)), confidence
