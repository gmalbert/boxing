# Model Edge Audit — KnockOutIQ

**Date:** 2026-07-25  
**Status:** 🔴 Critical — untrained model producing fake edges

---

## 1. Executive Summary

All 27 current "Elite" picks in `data_files/best_bets_today.json` have edges ranging from **7% to 45%**. These are not real predictive edges — they are artifacts of an **untrained model fallback** outputting ~50% win probability for nearly every fight, which when subtracted from heavily-skewed underdog implied probabilities produces absurdly inflated edges.

**Root cause:** `data_files/models/` does not exist on disk. Neither `logistic_model.pkl` nor `xgboost_model.pkl` have ever been generated. Both `predict_proba()` functions fall through to a hardcoded heuristic. Additionally, `export_best_bets.py` falls back to raw Elo (which defaults to 1500 for most fighters from The Odds API), producing 50/50 splits for unknown fighters.

**The picks should not be trusted or acted upon until the models are trained.**

---

## 2. Root Cause: The Untrained Fallback

### 2.1 No Trained Model Files Exist

`models/logistic_model.py:50-54` — `load()` checks for `data_files/models/logistic_model.pkl`:
```python
def load() -> Optional[Pipeline]:
    if _MODEL_PATH.exists():
        return joblib.load(_MODEL_PATH)
    return None
```

`models/xgboost_model.py:61-65` — same pattern for `data_files/models/xgboost_model.pkl`:
```python
def load() -> Optional[dict]:
    if _MODEL_PATH.exists():
        return joblib.load(_MODEL_PATH)
    return None
```

The `data_files/models/` directory **does not exist** on disk. No model pickle has ever been created because no training pipeline exists in CI/CD. The `fetch_data.yml` workflow runs `precache_predictions.py` and `export_best_bets.py` but **never calls `logistic_model.train()` or `xgboost_model.train()`**.

### 2.2 The Heuristic Fallback

When `load()` returns `None`, both models fall through to `_heuristic_prob()` (`models/logistic_model.py:71-89`):

```python
def _heuristic_prob(features: dict) -> float:
    weights = {
        "elo_diff": 0.35, "win_pct_diff": 0.25, "reach_diff": 0.15,
        "ko_pct_diff": 0.10, "age_diff": -0.08, "opposition_quality_diff": 0.07,
    }
    score = sum(features.get(k, 0.0) * w for k, w in weights.items())
    prob = 1 / (1 + np.exp(-score / 100))  # ← division by 100 flattens everything
    return float(np.clip(prob, 0.05, 0.95))
```

The `score / 100` divisor ensures the sigmoid stays in its linear region for all realistic feature values. Example: a massive 500-point Elo difference (already near-impossible) produces `score = 500 * 0.35 = 175`, then `sigmoid(175/100) = sigmoid(1.75) ≈ 0.85`. Most real feature differentials produce scores in the single digits, yielding probabilities **tightly clustered around 50%**.

### 2.3 The Elo Fallback in export_best_bets.py

`scripts/export_best_bets.py:93-107` — when `ModelPrediction` rows don't exist in the DB (no model ever saved them), the script falls back to pure Elo:

```python
if pred and pred.fighter_a_win_prob is not None:
    model_prob_a = float(pred.fighter_a_win_prob)
else:
    # Fall back to Elo heuristic
    elo_a = fa.elo_rating or 1500.0
    elo_b = fb.elo_rating or 1500.0
    model_prob_a = _elo_win_prob(elo_a, elo_b)
```

Most fighters fetched from The Odds API have no Elo history, so both default to **1500**, producing `elo_win_prob(1500, 1500) = 0.50`. This is why 22 of 27 picks show `confidence: 0.5`.

### 2.4 Dead Features Compound the Problem

`scripts/precache_predictions.py:36-49` — 3 of 9 features are hardcoded to zero:

```python
"age_diff": 0,                        # birth_date available but never subtracted
"days_since_last_fight_diff": 0,      # last_fight_date never populated
"opposition_quality_diff": 0,         # opponent Elo average never computed
```

The 5 XGBoost-extended features (`rolling_win_rate_diff`, `recent_ko_pct_diff`, `avg_rounds_fought_diff`, `title_fight`, `weight_class_encoded`) are never computed by any feature builder. So even if XGBoost loaded successfully, it would receive zeros for half its features.

---

## 3. How Fake Edges Are Created

### The Math

```python
# utils/odds_utils.py:66-72
def calculate_edge(model_prob, dk_american_odds):
    dk_implied = american_to_implied_prob(dk_american_odds)
    return model_prob - dk_implied
```

### Worked Example: Cesar Diaz (+2000)

| Step | Value |
|------|-------|
| Model win probability | 0.5000 (Elo fallback, both fighters at 1500) |
| DK American odds | +2000 |
| DK implied probability | `100 / (2000 + 100)` = **0.0476** (4.76%) |
| **Edge** | `0.5000 - 0.0476` = **0.4524 (45.24%)** |

The model says Diaz has a coin-flip chance. DK prices him as a 4.76% underdog. The difference is purely the model's ignorance, not a real market inefficiency.

### All 27 Current Picks — Edge Breakdown

Every single pick is on the **underdog side** because the heuristic's ~50% always exceeds the favorite's high implied probability, making the edge on the favorite negative. This is a structural bias, not insight.

| Fight | Pick | Model Prob | DK Odds | DK Implied | **Edge** |
|-------|------|-----------|---------|------------|----------|
| Nishant Dev vs Cesar Diaz | Cesar Diaz | 0.5000 | +2000 | 4.76% | **45.24%** |
| Oleksandr Khyzhniak vs Lenny Patrach | Lenny Patrach | 0.5000 | +1200 | 7.69% | **42.31%** |
| Mikie Tallon vs Orlando Pino | Orlando Pino | 0.5000 | +1200 | 7.69% | **42.31%** |
| Callum Peters vs Ivan Ricardo Actis | Ivan Ricardo Actis | 0.5000 | +1100 | 8.33% | **41.67%** |
| Jacob Bank vs Pawel August | Pawel August | 0.5000 | +750 | 11.76% | **38.24%** |
| Richardson Hitchins vs Ricardo Salas Rodriguez | Ricardo Salas Rodriguez | 0.5000 | +650 | 13.33% | **36.67%** |
| Reito Tsutsumi vs Alvino Herrera Meza | Alvino Herrera Meza | 0.5000 | +643 | 13.46% | **36.54%** |
| Royston Barney-Smith vs Reece Bellotti | Reece Bellotti | 0.5459 | +425 | 19.05% | **35.54%** |
| Troy Nash vs Ethan Perez | Ethan Perez | 0.5000 | +500 | 16.67% | **33.33%** |
| Paulo Aokuso vs Luis Antonio Tejeda | Luis Antonio Tejeda | 0.5000 | +450 | 18.18% | **31.82%** |
| Steven Cairns vs Senan Kelly | Senan Kelly | 0.5000 | +425 | 19.05% | **30.95%** |
| Josh Kelly vs Caoimhin Agyarko | Caoimhin Agyarko | 0.5000 | +330 | 23.26% | **26.74%** |
| Anthony Joshua vs Kristian Prenga | Kristian Prenga | 0.3418 | +1100 | 8.33% | **25.85%** |
| Tyson Fury vs Mariusz Wach | Mariusz Wach | 0.2944 | +2500 | 3.85% | **25.59%** |
| Edgar Berlanga vs Steven Butler | Steven Butler | 0.4324 | +280 | 26.32% | **16.92%** |
| Arnold Gonzalez vs Emiliano Moreno | Arnold Gonzalez | 0.5000 | +200 | 33.33% | **16.67%** |
| Paul Fleming vs Ahmad Reda | Paul Fleming | 0.5000 | +195 | 33.90% | **16.10%** |
| Pierce O'Leary vs Mark Chamberlain | Mark Chamberlain | 0.5000 | +193 | 34.13% | **15.87%** |
| Kashaun Davis vs Mihai Nistor | Mihai Nistor | 0.5000 | +185 | 35.09% | **14.91%** |
| Otto Wallin vs Vladyslav Sirenko | Vladyslav Sirenko | 0.5000 | +170 | 37.04% | **12.96%** |
| Stephen Fulton vs Liam Wilson | Liam Wilson | 0.4417 | +220 | 31.25% | **12.92%** |
| Hamzah Sheeraz vs Simon Zachenhuber | Simon Zachenhuber | 0.2100 | +870 | 10.31% | **10.69%** |
| Dominique Francis vs Hector Andres Sosa | Hector Andres Sosa | 0.5000 | +150 | 40.00% | **10.00%** |
| Sergiy Derevyanchenko vs Jalil Hackett | Sergiy Derevyanchenko | 0.4659 | +160 | 38.46% | **8.13%** |
| Gary Cully vs Lee Reeves | Lee Reeves | 0.5000 | +134 | 42.74% | **7.26%** |
| Lamont Roach vs William Zepeda | William Zepeda | 0.5000 | +134 | 42.74% | **7.26%** |
| Raymond Muratalla vs Robson Conceicao | Robson Conceicao | 0.2274 | +540 | 15.63% | **7.12%** |

**Key observation:** 22 of 27 picks have `model_prob = 0.5000` — pure Elo default with no differentiation. The remaining 5 have slight deviations from Elo (fighters with non-default ratings), but the underlying problem is identical.

---

## 4. Contributing Factors

### 4.1 No Training Pipeline

Both `logistic_model.train()` (`models/logistic_model.py:41-47`) and `xgboost_model.train()` (`models/xgboost_model.py:51-58`) are implemented and correct, but **nothing calls them**. The entire CI/CD pipeline (`.github/workflows/fetch_data.yml`) runs daily:
1. `fetch_historical_data.py` — fetches odds/schedule
2. `precache_predictions.py` — runs prediction using untrained fallback
3. `export_best_bets.py` — generates picks using untrained fallback

There is no step to load historical fight data, build a training set, call `train()`, and persist the pickles. The models exist in code only.

### 4.2 Dead Features (3 of 9 logistic, 8 of 14 XGBoost)

Features hardcoded to zero in `_build_features()` (`scripts/precache_predictions.py:36-49`):

| Feature | Status | Why Dead |
|---------|--------|----------|
| `age_diff` | Always 0 | `birth_date` exists on Fighter model but never subtracted |
| `days_since_last_fight_diff` | Always 0 | `last_fight_date` never populated |
| `opposition_quality_diff` | Always 0 | Opponent Elo aggregation never implemented |
| `rolling_win_rate_diff` | Always 0 | Never computed (XGBoost-only) |
| `recent_ko_pct_diff` | Always 0 | Never computed (XGBoost-only) |
| `avg_rounds_fought_diff` | Always 0 | Never computed (XGBoost-only) |
| `title_fight` | Always 0 | Never computed (XGBoost-only) |
| `weight_class_encoded` | Always 0 | Never computed (XGBoost-only) |

Only 5 features carry real signal: `reach_diff`, `height_diff`, `win_pct_diff`, `ko_pct_diff`, and `elo_diff`. `is_southpaw_matchup` is rarely non-zero since most fighters default to "Orthodox".

### 4.3 Confidence Metric Is Not Statistical

`models/xgboost_model.py:88`:
```python
confidence = abs(prob - 0.5) * 2
```

This is a simple distance-from-coin-flip metric, not a statistical confidence interval or prediction variance. It has no relationship to actual calibration error or prediction uncertainty. A model outputting 0.95 on a true 50/50 fight gets "confidence 0.90".

### 4.4 No Calibration, No Validation, No Backtesting

The `MODEL_SUGGESTED_ENHANCEMENTS.md` file acknowledges these gaps explicitly:

- **No Platt scaling or isotonic regression** — probabilities are uncalibrated
- **No Brier score tracking** — listed as a target ("< 0.20") but never implemented
- **No cross-validation** — `train()` has no validation split, no k-fold
- **No backtesting framework** — the calibration chart on the Model Dashboard (`pages/05_Model_Dashboard.py:193-216`) is the only evaluation, and it relies on the same untrained predictions in the DB
- **No CLV tracking** — infrastructure exists (`BetLog.clv` column, `clv()` function) but nothing populates it

### 4.5 Small Data Problem

The seed data contains ~75 historical fights and ~85 fighters. This is orders of magnitude too small for an XGBoost model with 200 trees and 14 features. The docs warn: "Overfitting is a real risk. Use cross-validation aggressively." — but it was never implemented.

---

## 5. Recommendations

### 🔴 Critical: Fix the Broken Pipeline (Do These First)

**1. Create a model training script and add it to CI/CD.**

Create `scripts/train_models.py` that:
- Loads all completed fights with results from the DB
- Builds feature vectors for each fight
- Calls `logistic_model.train(X, y)` and `xgboost_model.train(X, y)`
- Saves pickle files to `data_files/models/`

Add it to `.github/workflows/fetch_data.yml` in the weekly job (after Elo recalculation, before precaching):
```yaml
- name: Train prediction models
  run: python scripts/train_models.py
```

**2. Add a safety check to `export_best_bets.py`.**

Before generating picks, verify that at least one model loaded successfully:
```python
if not Path("data_files/models/logistic_model.pkl").exists() and \
   not Path("data_files/models/xgboost_model.pkl").exists():
    print("[boxing export] WARNING: No trained models found. Edges will be unreliable.")
    # Option: exit with error, or write empty output
```

**3. Cap heuristic edges when fallback is active.**

When `_heuristic_prob()` or `_elo_win_prob()` is the active prediction path, clamp the output edge to 0 so no fake picks propagate to `best_bets_today.json`. Alternatively, set `confidence` to 0 to signal that the model has no opinion.

### 🟡 High Priority: Model Quality

**4. Wire up the dead features.**

- `age_diff`: compute `(fa.birth_date - fb.birth_date)` in years from the `birth_date` column
- `days_since_last_fight_diff`: populate `last_fight_date` from the fight results pipeline, then subtract
- `opposition_quality_diff`: average opponent Elo from fight history
- XGBoost features: compute rolling win rates from recent fights, extract title_fight from fight metadata, encode weight class

**5. Add Platt scaling calibration.**

After training, fit a `CalibratedClassifierCV` wrapper or apply `sklearn.calibration.CalibratedClassifierCV(method='sigmoid')` to both models. This ensures `predict_proba()` outputs are well-calibrated probabilities.

**6. Track Brier score and log-loss.**

Add to the Model Dashboard:
- Brier score per model version
- Log-loss per model version
- Display in a table alongside accuracy

**7. Add train/test split with cross-validation.**

In `train_models.py`:
- Split historical data chronologically (train on older fights, test on newer)
- Run 5-fold cross-validation
- Log metrics per fold
- Save the best-performing model

### 🟢 Medium Priority: Confidence & Monitoring

**8. Replace the fake confidence metric.**

Instead of `abs(prob - 0.5) * 2`, use one of:
- Prediction intervals from bootstrapped ensemble predictions
- Standard deviation across XGBoost tree outputs
- Calibration-based confidence (distance from calibrated probability to decision boundary)

**9. Implement backtesting.**

Create a script that replays the model chronologically through historical fights and tracks:
- Cumulative edge vs. actual win rate
- ROI by edge tier
- Calibration drift over time

**10. Add CLV tracking.**

Populate `BetLog.clv` by comparing the odds at bet time to closing DraftKings lines. Positive CLV over time is the best validation that edges are real.

---

## 6. Verification Steps

After implementing the fixes above:

1. **Confirm models exist on disk** — `ls data_files/models/` should show `logistic_model.pkl` and `xgboost_model.pkl`
2. **Run precaching** — `python scripts/precache_predictions.py` should show probabilities significantly different from 0.50
3. **Check edge distribution** — edges should fall to realistic ranges (< 15%), with some negative edges and a mix of favorite/underdog picks
4. **Verify calibration chart** — the Model Dashboard reliability diagram should show diagonal alignment (predicted probability ≈ actual win rate)
5. **Run export** — `python scripts/export_best_bets.py` should produce a mix of picks, not 100% underdogs
6. **Spot-check a few picks** — manually verify that the model probability for a heavy favorite (e.g., Tyson Fury) is appropriately high (≥ 80%), not 30%

---

## 7. Additional Notes

- The `MODEL_SUGGESTED_ENHANCEMENTS.md` document (`docs/MODEL_SUGGESTED_ENHANCEMENTS.md`) was written with awareness of most of these issues. It predates this audit and lists calibration, cross-validation, Brier score, recency weighting, and feature engineering as needed. It should be treated as a roadmap alongside this audit.
- The Elo rating system (`models/elo.py`) is well-implemented and appropriate for boxing. Once models are trained, Elo will be a valuable feature. The problem is that Elo alone (with default 1500s) is being used as the sole prediction engine.
- The Streamlit UI (`pages/05_Model_Dashboard.py`) already has the calibration chart and accuracy tab scaffolding — once real predictions flow through, these visualizations will become genuinely useful.
