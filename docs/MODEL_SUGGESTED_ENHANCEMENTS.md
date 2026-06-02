# KnockOutIQ — Model Suggested Enhancements

## Priority 1: Core Model Accuracy

### Calibration
- Evaluate logistic regression and Elo models with `calibration_curve` from scikit-learn. Current models are not post-calibrated.
- Apply **Platt scaling** on logistic regression outputs and **isotonic regression** on Elo-derived probabilities.
- Target Brier score < 0.20 for fight winner prediction.

### Style Matchup Feature
- Encode `style_tag` (e.g., "brawler", "boxer-puncher", "southpaw") as categorical features.
- Add `style_advantage` binary flag: known style mismatches (e.g., southpaw vs. righty orthodox) have documented historical edges.

### Recency Weighting
- Downweight fights older than 18 months in the training set. Boxing careers have natural peaks; a 2019 KO win is less predictive than a 2024 one.
- Implement exponential decay: `weight = exp(-λ * months_ago)` with λ ≈ 0.04.

## Priority 2: Feature Engineering

### Weight Class Adjustment
- Normalise fighter stats (KO%, win rate) within weight class, not globally. A 40% KO rate is exceptional in Heavyweight but average in Bantamweight.

### Comeback Factor
- Binary flag for fighters returning from ≥12-month layoff (historically underperform vs. active fighters).

### Title Fight Effect
- Title fights (higher pressure, often conservative game-planning) have lower KO rates than non-title fights. Add `is_title_fight` as explicit feature.

### Venue / Crowd Advantage
- Hometown crowd support correlates with judge scoring in close decisions. Add `is_home_fighter_a` and `is_neutral_venue` binary flags.

## Priority 3: Bet Type Expansion

### Method of Victory Model
- Separate XGBoost model targeting `{KO, TKO, Decision, DQ}` as a 4-class classification.
- Input features: punch output metrics, round betting lines, historical finishing rate.

### Round Betting Model
- Use existing round duration data to train a model on `{early_stoppage, mid_fight, late_or_distance}`.
- Feeds into DraftKings "Fight to go the distance" prop market.

## Priority 4: Infrastructure

### Rolling CLV Tracking
- Compare prediction odds at time of post to closing DraftKings line. Track CLV weekly.

### Automatic Model Versioning
- Store `model_version` with each `ModelPrediction` row to enable A/B comparison in the dashboard.
