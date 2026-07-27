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

from sklearn.calibration import CalibratedClassifierCV
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
        eval_metric="logloss",
        random_state=42,
    )


def train(X: pd.DataFrame, y: pd.Series) -> object:
    """Train and save the XGBoost model with Platt scaling calibration."""
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    available_cols = [c for c in EXTENDED_FEATURE_COLS if c in X.columns]
    base_model = _build_model()

    # Wrap with Platt scaling so predict_proba outputs are well-calibrated.
    n_cv = min(5, len(X) // 4)
    if n_cv >= 2:
        model = CalibratedClassifierCV(base_model, method="sigmoid", cv=n_cv)
        model.fit(X[available_cols], y)
    else:
        model = base_model
        model.fit(X[available_cols], y)

    # When using CalibratedClassifierCV, the wrapper's predict_proba returns
    # calibrated probabilities but the raw base estimator is still accessible
    # for confidence estimation via log-odds magnitude.
    base_clf = model
    if hasattr(model, "calibrated_classifiers_"):
        cc = model.calibrated_classifiers_[0]
        base_clf = getattr(cc, "base_estimator", getattr(cc, "estimator", model))

    joblib.dump({"model": model, "base_clf": base_clf, "features": available_cols, "version": _VERSION}, _MODEL_PATH)
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

    Confidence is based on the raw log-odds magnitude from the uncalibrated
    XGBoost base classifier, mapped to [0, 1] via sigmoid. This captures
    the model's conviction before Platt scaling flattens extreme predictions,
    so a calibrated 85% with weak raw log-odds gets lower confidence than
    one pushed by a genuinely wide margin.
    """
    if bundle is None:
        bundle = load()

    if bundle is None or not _XGB_AVAILABLE:
        prob = _heuristic_prob(features)
        confidence = 0.0
        return prob, confidence

    model = bundle["model"]
    base_clf = bundle.get("base_clf", None)
    feat_cols = bundle["features"]
    row = pd.DataFrame([{col: features.get(col, 0.0) for col in feat_cols}])
    prob = float(model.predict_proba(row)[0][1])

    # Compute confidence from raw log-odds of the uncalibrated booster.
    # CalibratedClassifierCV wraps predict_proba through Platt scaling, but the
    # raw base model output reflects genuine model conviction.
    if base_clf is not None:
        raw_proba = base_clf.predict_proba(row[feat_cols])[0]
        raw_prob_a = float(raw_proba[1])
        raw_prob_a = np.clip(raw_prob_a, 1e-6, 1 - 1e-6)
        raw_logodds = np.log(raw_prob_a / (1 - raw_prob_a))
        L = 4.0  # log-odds scale; ±4 → ~0.98 confidence, ±2 → ~0.46
        confidence = 2.0 / (1.0 + np.exp(-abs(raw_logodds) / L)) - 1.0
    else:
        confidence = abs(prob - 0.5) * 2

    return float(np.clip(prob, 0.05, 0.95)), float(np.clip(confidence, 0.0, 1.0))
